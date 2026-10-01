import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

import config

logger = logging.getLogger(__name__)


async def check_subscription(user_id, context):
    if not config.CHANNEL_ID:
        return True
    try:
        member = await context.bot.get_chat_member(config.CHANNEL_ID, user_id)
        if member.status in ('member', 'administrator', 'creator'):
            return True
        return member.status == 'restricted' and bool(getattr(member, 'is_member', False))
    except TelegramError as e:
        logger.warning(f"Subscription check error: {e}")
        return False


async def send_subscription_required(chat_id, context):
    keyboard = []
    channel_name = config.CHANNEL_USERNAME.lstrip('@')
    if channel_name:
        keyboard.append([InlineKeyboardButton("📢 Subscribe", url=f"https://t.me/{channel_name}")])
    keyboard.append([InlineKeyboardButton("✅ I subscribed", callback_data="check_subscription")])

    await context.bot.send_message(
        chat_id=chat_id,
        text="📢 <b>To use the bot, subscribe to our channel</b>\n\nAfter subscribing, press the button below.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
