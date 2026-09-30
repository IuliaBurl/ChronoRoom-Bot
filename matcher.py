import json
import logging
from database import Database

class MatchMaker:
    def __init__(self):
        self.db = Database()
        self.MATCH_SIZE = 7

    def calculate_compatibility(self, answers1_data, answers2_data):
        try:
            if isinstance(answers1_data, str):
                answers1 = json.loads(answers1_data)
            else:
                answers1 = answers1_data

            if isinstance(answers2_data, str):
                answers2 = json.loads(answers2_data)
            else:
                answers2 = answers2_data

            if isinstance(answers1, str):
                answers1 = json.loads(answers1)
            if isinstance(answers2, str):
                answers2 = json.loads(answers2)

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logging.error(f"Error parsing answers: {e}")
            return 0

        if not answers1 or not answers2:
            return 0

        common_answers = 0
        total_questions = min(len(answers1), len(answers2))

        for i in range(total_questions):
            answer1 = answers1.get(f'q{i}')
            answer2 = answers2.get(f'q{i}')

            if answer1 is not None and answer2 is not None and answer1 == answer2:
                common_answers += 1

        return common_answers / total_questions if total_questions > 0 else 0

    def find_best_match_group(self, test_type):
        users_in_queue = self.db.get_users_in_queue_by_type(test_type)

        logging.info(f"Users in {test_type} queue: {len(users_in_queue)}")

        if len(users_in_queue) < self.MATCH_SIZE:
            return None

        selected_users = users_in_queue[:self.MATCH_SIZE]
        user_ids = [user[0] for user in selected_users]

        logging.info(f"Creating {test_type} match with users: {user_ids}")

        match_id = self.db.create_match(user_ids, test_type)

        for user_id in user_ids:
            self.db.remove_from_queue(user_id)

        return {
            'match_id': match_id,
            'users': selected_users,
            'test_type': test_type
        }

    def generate_match_stats(self, users_data):
        stats = []

        for i, user1 in enumerate(users_data):
            user1_id, username1, first_name1, answers1_data = user1

            for j, user2 in enumerate(users_data[i+1:], i+1):
                user2_id, username2, first_name2, answers2_data = user2

                compatibility = self.calculate_compatibility(answers1_data, answers2_data)

                user1_display = first_name1
                user2_display = first_name2

                stats.append({
                    'user1': user1_display,
                    'user2': user2_display,
                    'compatibility': round(compatibility * 100, 1)
                })

        return stats
