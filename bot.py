import logging
import re
import time
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters

import config
import basic_test_questions
import career_test_questions
import force_test_questions
import castle_test_questions
import relationships_test_questions
import philosophical_test_questions
from subscription import check_subscription, send_subscription_required
from database import Database
from matcher import MatchMaker

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

user_last_messages = {}
user_test_progress = {}
active_matches = {}
db = Database()
matcher = MatchMaker()

MATCH_TTL = 24 * 60 * 60
GROUP_LINK_PATTERN = re.compile(r'^(?:https?://)?t\.me/(?:\+[\w-]+|joinchat/[\w-]+|[A-Za-z][\w]{3,})$')

TEST_NAMES = {
    'basic': '🏠 Basic Test',
    'career': '💼 Career Test',
    'force': '🚀 Force Test',
    'castle': '🏰 Dream Castle',
    'relationships': '❤️ Relationships Test',
    'philosophical': '🧠 Philosophical Test'
}

TEST_QUESTIONS = {
    "basic_test": ("basic", basic_test_questions.BASIC_TEST_QUESTIONS),
    "career_test": ("career", career_test_questions.CAREER_TEST_QUESTIONS),
    "force_test": ("force", force_test_questions.FORCE_TEST_QUESTIONS),
    "castle_test": ("castle", castle_test_questions.CASTLE_TEST_QUESTIONS),
    "relationships_test": ("relationships", relationships_test_questions.RELATIONSHIPS_TEST_QUESTIONS),
    "philosophical_test": ("philosophical", philosophical_test_questions.PHILOSOPHICAL_TEST_QUESTIONS)
}


def display_name(first_name, username, user_id):
    if first_name:
        return first_name
    if username:
        return f"@{username}"
    return str(user_id)


async def delete_previous_messages(chat_id, context):
    if chat_id in user_last_messages:
        for message_id in user_last_messages[chat_id]:
            try:
                await context.bot.delete_message(chat_id, message_id)
            except BadRequest:
                pass
        user_last_messages[chat_id] = []


async def send_and_track_message(chat_id, text, context, reply_markup=None, parse_mode='HTML'):
    await delete_previous_messages(chat_id, context)

    message = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )

    user_last_messages[chat_id] = [message.message_id]
    return message


def prune_matches():
    now = time.time()
    expired = [match_id for match_id, data in active_matches.items()
               if now - data['created_at'] > MATCH_TTL]
    for match_id in expired:
        del active_matches[match_id]


async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id

    context.user_data.pop('waiting_for_group_link', None)
    context.user_data.pop('match_id', None)

    if not await check_subscription(user.id, context):
        await send_subscription_required(chat_id, context)
        return

    welcome_text = (
        f"🌟 <b>Welcome to ChronoRoom, {escape(user.first_name or '')}!</b>\n\n"
        "Take a test and find 6 people with similar interests! ✨"
    )

    keyboard = [
        [InlineKeyboardButton("🏠 Basic Test", callback_data="basic_test")],
        [InlineKeyboardButton("💼 Career Test", callback_data="career_test")],
        [InlineKeyboardButton("🚀 Force Test", callback_data="force_test")],
        [InlineKeyboardButton("🏰 Dream Castle", callback_data="castle_test")],
        [InlineKeyboardButton("❤️ Relationships Test", callback_data="relationships_test")],
        [InlineKeyboardButton("🧠 Philosophical Test", callback_data="philosophical_test")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_and_track_message(chat_id, welcome_text, context, reply_markup)


async def faststart(update: Update, context: CallbackContext):
    user = update.effective_user

    if user.id != config.OWNER_ID:
        await update.message.reply_text("❌ This command is for the bot owner only")
        return

    test_user_ids = [999000001, 999000002, 999000003, 999000004, 999000005, 999000006]
    for user_id in test_user_ids:
        db.remove_from_queue(user_id)

    queue_counts = {
        test_type: len(db.get_users_in_queue_by_type(test_type))
        for test_type in TEST_NAMES
    }

    ready_type = max(queue_counts, key=queue_counts.get)

    if queue_counts[ready_type] < 2:
        summary = "\n".join(
            f"• {TEST_NAMES[t]}: {c}" for t, c in queue_counts.items()
        )
        await update.message.reply_text(
            f"❌ <b>Not enough users in the queue</b>\n\n"
            f"Currently in queue:\n{summary}\n\n"
            "At least 2 people need to be in the queue of the same test.",
            parse_mode='HTML'
        )
        return

    original_size = matcher.MATCH_SIZE
    matcher.MATCH_SIZE = 2
    try:
        match_result = matcher.find_best_match_group(ready_type)
    finally:
        matcher.MATCH_SIZE = original_size

    if match_result:
        await notify_match_found(match_result, context)
        await update.message.reply_text(
            f"🚀 <b>Notifications sent to participants!</b>\n\n"
            f"Test: {TEST_NAMES[ready_type]}\n"
            "Now one of the participants needs to send the group link.",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "❌ <b>Could not find a suitable group</b>\n\n"
            "Check the logs for details.",
            parse_mode='HTML'
        )


async def handle_button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if not await check_subscription(user_id, context):
        await send_subscription_required(chat_id, context)
        return

    data = query.data

    if data in TEST_QUESTIONS:
        test_type, questions = TEST_QUESTIONS[data]
        await start_test(chat_id, context, query.from_user, test_type, questions)
    elif data == "check_subscription":
        await start(update, context)
    elif data.startswith("answer_"):
        parts = data.split('_')
        try:
            test_type = parts[1]
            question_index = int(parts[2])
            answer_index = int(parts[3])
        except (IndexError, ValueError):
            return
        await handle_test_answer(chat_id, context, user_id, test_type, question_index, answer_index)
    elif data == "join_search":
        await join_group_search(chat_id, context, user_id)
    elif data == "send_group_link":
        await handle_send_group_link(chat_id, context, user_id)
    elif data == "back_to_tests":
        await start(update, context)


async def start_test(chat_id, context, user, test_type, questions):
    user_test_progress[user.id] = {
        'test_type': test_type,
        'questions': questions,
        'current_question': 0,
        'answers': {},
        'username': user.username,
        'first_name': user.first_name
    }

    await show_question(chat_id, context, user.id)


async def show_question(chat_id, context, user_id):
    progress = user_test_progress[user_id]
    question_index = progress['current_question']
    questions = progress['questions']
    test_type = progress['test_type']

    if question_index >= len(questions):
        await finish_test(chat_id, context, user_id)
        return

    question_data = questions[question_index]
    question_text = escape(question_data['question'])
    options = [escape(option) for option in question_data['options']]

    options_text = "\n".join(f"{i + 1}. {option}" for i, option in enumerate(options))

    text = (
        f"{TEST_NAMES[test_type]}\n"
        f"❓ Question {question_index + 1}/{len(questions)}\n\n"
        f"{question_text}\n\n"
        f"{options_text}\n\n"
        "<b>Choose an option:</b>"
    )

    keyboard = [
        [InlineKeyboardButton(str(i + 1), callback_data=f"answer_{test_type}_{question_index}_{i}")]
        for i in range(len(options))
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_and_track_message(chat_id, text, context, reply_markup)


async def handle_test_answer(chat_id, context, user_id, test_type, question_index, answer_index):
    progress = user_test_progress.get(user_id)

    if not progress:
        await send_and_track_message(
            chat_id,
            "⌛ <b>This test session has expired.</b>\n\nSend /start to take the test again.",
            context
        )
        return

    if progress['test_type'] != test_type or progress['current_question'] != question_index:
        return

    options = progress['questions'][question_index]['options']
    if not 0 <= answer_index < len(options):
        return

    progress['answers'][f'q{question_index}'] = answer_index
    progress['current_question'] += 1

    await show_question(chat_id, context, user_id)


async def finish_test(chat_id, context, user_id):
    progress = user_test_progress.pop(user_id, None)
    if not progress:
        return

    test_type = progress['test_type']

    db.save_user_test(
        user_id,
        progress['username'],
        progress['first_name'],
        progress['answers'],
        test_type
    )

    text = (
        f"🎉 <b>{TEST_NAMES[test_type]} completed!</b>\n\n"
        "Your answers have been saved. Want to find a group of like-minded people?\n\n"
        f"Once {matcher.MATCH_SIZE} participants are gathered - we'll create a chat and show match statistics! 🔥"
    )

    keyboard = [
        [InlineKeyboardButton("🔍 Find a group", callback_data="join_search")],
        [InlineKeyboardButton("🔄 Take another test", callback_data="back_to_tests")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_and_track_message(chat_id, text, context, reply_markup)


async def join_group_search(chat_id, context, user_id):
    user_data = db.get_user(user_id)
    if not user_data:
        await send_and_track_message(
            chat_id,
            "❌ <b>Take a test first!</b>\n\n"
            "To find a group, you need to take any test first.",
            context
        )
        return

    test_type = user_data['test_type']
    db.add_to_match_queue(user_id, test_type)

    users_in_queue = len(db.get_users_in_queue_by_type(test_type))

    text = (
        f"🔍 <b>You've joined the search queue!</b>\n\n"
        f"Currently in queue: {users_in_queue}/{matcher.MATCH_SIZE} participants\n\n"
        f"Once {matcher.MATCH_SIZE} participants are gathered - we'll create a group and send you an invitation.\n\n"
        "Wait for the notification! ⏳"
    )

    await send_and_track_message(chat_id, text, context)

    match_result = matcher.find_best_match_group(test_type)
    if match_result:
        await notify_match_found(match_result, context)


async def notify_match_found(match_data, context):
    prune_matches()

    match_id = match_data['match_id']
    users = match_data['users']
    test_type = match_data['test_type']

    active_matches[match_id] = {
        'users': users,
        'test_type': test_type,
        'link_sent': False,
        'sent_by': None,
        'created_at': time.time()
    }

    stats = matcher.generate_match_stats(users)
    top_stats = sorted(stats, key=lambda stat: stat['compatibility'], reverse=True)[:5]

    user_list = "\n".join(
        f"• {escape(display_name(user[2], user[1], user[0]))}" for user in users
    )

    notification_text = (
        f"🎉 <b>Group found! ({TEST_NAMES[test_type]})</b>\n\n"
        f"<b>Participants:</b>\n{user_list}\n\n"
        "<b>Top matches:</b>\n"
    )

    for stat in top_stats:
        notification_text += (
            f"• {escape(str(stat['user1']))} ↔ {escape(str(stat['user2']))} - {stat['compatibility']}%\n"
        )

    notification_text += (
        "\n<b>Whoever creates the group first - send the link here!</b>\n"
        "Only one participant can send the link, after which the queue will close."
    )

    keyboard = [
        [InlineKeyboardButton("📎 Send group link", callback_data="send_group_link")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_count = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user[0],
                text=notification_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            sent_count += 1
            logger.info(f"✅ Notification sent to user {user[2]} (ID: {user[0]})")
        except Exception as e:
            logger.error(f"❌ Error sending notification to user {user[0]}: {e}")

    logger.info(f"📨 Total notifications sent: {sent_count}")


async def handle_send_group_link(chat_id, context, user_id):
    prune_matches()

    user_matches = [
        (match_id, match_data)
        for match_id, match_data in reversed(list(active_matches.items()))
        if any(user[0] == user_id for user in match_data['users'])
    ]

    target_match_id = None
    target_match_data = None
    for match_id, match_data in user_matches:
        if not match_data['link_sent']:
            target_match_id, target_match_data = match_id, match_data
            break
    if target_match_id is None and user_matches:
        target_match_id, target_match_data = user_matches[0]

    if not target_match_id:
        await send_and_track_message(
            chat_id,
            "❌ <b>No active match found</b>\n\n"
            "The group may have already been created or the waiting time has expired.",
            context
        )
        return

    if target_match_data['link_sent']:
        await send_and_track_message(
            chat_id,
            "❌ <b>The link has already been sent!</b>\n\n"
            f"The group link was already sent by {escape(str(target_match_data['sent_by']))}.\n"
            "Wait for the invitation in your direct messages.",
            context
        )
        return

    text = (
        "🔗 <b>Send the link to the created group</b>\n\n"
        "Copy the invite link from the group settings and send it here.\n\n"
        "<i>How to get the link:</i>\n"
        "1. Open the group settings\n"
        "2. Click 'Invite to group via link'\n"
        "3. Copy the link and send it here\n\n"
        "<b>Attention:</b> Only the first sent option will be accepted!"
    )

    context.user_data['waiting_for_group_link'] = True
    context.user_data['match_id'] = target_match_id

    await send_and_track_message(chat_id, text, context)


async def handle_group_link(update: Update, context: CallbackContext):
    if not context.user_data.get('waiting_for_group_link'):
        return

    group_link = update.message.text.strip()

    if not GROUP_LINK_PATTERN.match(group_link):
        await update.message.reply_text(
            "❌ <b>This doesn't look like a Telegram group link</b>\n\n"
            "Send only the link in the format: https://t.me/+... or https://t.me/groupname",
            parse_mode='HTML'
        )
        return

    if not group_link.startswith('http'):
        group_link = 'https://' + group_link

    match_id = context.user_data.get('match_id')

    if match_id not in active_matches or active_matches[match_id]['link_sent']:
        await update.message.reply_text(
            "❌ <b>The link has already been sent!</b>\n\n"
            "Someone has already sent a link to the group.",
            parse_mode='HTML'
        )
        context.user_data.pop('waiting_for_group_link', None)
        return

    match_users = active_matches[match_id]['users']
    user_name = update.effective_user.first_name or str(update.effective_user.id)

    active_matches[match_id]['link_sent'] = True
    active_matches[match_id]['sent_by'] = user_name

    sent_invites = 0
    for user_data in match_users:
        try:
            await context.bot.send_message(
                chat_id=user_data[0],
                text=f"🎉 <b>Group invitation!</b>\n\n"
                     f"The group was created by {escape(user_name)}! 🚀\n\n"
                     f"Join using the link:\n"
                     f"{escape(group_link)}\n\n"
                     f"See you inside! 👋",
                parse_mode='HTML'
            )
            sent_invites += 1
            logger.info(f"📨 Invitation sent to user {user_data[2]}")
        except Exception as e:
            logger.error(f"❌ Error sending invitation to user {user_data[0]}: {e}")

        db.remove_from_queue(user_data[0])

    context.user_data.pop('waiting_for_group_link', None)
    context.user_data.pop('match_id', None)

    await update.message.reply_text(
        f"✅ <b>Invitations sent!</b>\n\n"
        f"Total invitations sent: {sent_invites}\n\n"
        f"Group successfully created! 🎉",
        parse_mode='HTML'
    )

    logger.info(f"📨 Total invitations sent: {sent_invites}")


async def error_handler(update: object, context: CallbackContext):
    logger.error("Unhandled error", exc_info=context.error)


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")

    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("faststart", faststart))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_link))
    application.add_error_handler(error_handler)

    print("Bot started! 🚀")
    application.run_polling()


if __name__ == "__main__":
    main()
