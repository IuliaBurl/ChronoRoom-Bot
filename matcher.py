import json
import logging
import threading

from database import Database


class MatchMaker:
    def __init__(self):
        self.db = Database()
        self.MATCH_SIZE = 7
        self.lock = threading.Lock()

    @staticmethod
    def _parse_answers(data):
        try:
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, str):
                data = json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            logging.error(f"Error parsing answers: {e}")
            return None
        if isinstance(data, list):
            return {f'q{i}': value for i, value in enumerate(data)}
        if isinstance(data, dict):
            return data
        return None

    @staticmethod
    def _compare(answers1, answers2):
        if not answers1 or not answers2:
            return 0
        total_questions = min(len(answers1), len(answers2))
        if total_questions == 0:
            return 0
        common_answers = 0
        for i in range(total_questions):
            answer1 = answers1.get(f'q{i}')
            answer2 = answers2.get(f'q{i}')
            if answer1 is not None and answer2 is not None and answer1 == answer2:
                common_answers += 1
        return common_answers / total_questions

    def calculate_compatibility(self, answers1_data, answers2_data):
        answers1 = self._parse_answers(answers1_data)
        answers2 = self._parse_answers(answers2_data)
        return self._compare(answers1, answers2)

    def _select_group(self, users):
        parsed = {user[0]: self._parse_answers(user[3]) for user in users}
        seed = users[0]
        group = [seed]
        candidates = list(users[1:])
        while len(group) < self.MATCH_SIZE and candidates:
            best = max(
                candidates,
                key=lambda candidate: sum(
                    self._compare(parsed[candidate[0]], parsed[member[0]])
                    for member in group
                )
            )
            group.append(best)
            candidates.remove(best)
        return group

    def find_best_match_group(self, test_type):
        with self.lock:
            users_in_queue = self.db.get_users_in_queue_by_type(test_type)
            logging.info(f"Users in {test_type} queue: {len(users_in_queue)}")

            if len(users_in_queue) < self.MATCH_SIZE:
                return None

            selected_users = self._select_group(users_in_queue)
            user_ids = [user[0] for user in selected_users]

            logging.info(f"Creating {test_type} match with users: {user_ids}")

            match_id = self.db.create_match(user_ids, test_type)

            return {
                'match_id': match_id,
                'users': selected_users,
                'test_type': test_type
            }

    def generate_match_stats(self, users_data):
        stats = []

        for i, user1 in enumerate(users_data):
            user1_id, username1, first_name1, answers1_data = user1

            for user2 in users_data[i + 1:]:
                user2_id, username2, first_name2, answers2_data = user2

                compatibility = self.calculate_compatibility(answers1_data, answers2_data)

                user1_display = first_name1 or (f"@{username1}" if username1 else str(user1_id))
                user2_display = first_name2 or (f"@{username2}" if username2 else str(user2_id))

                stats.append({
                    'user1': user1_display,
                    'user2': user2_display,
                    'compatibility': round(compatibility * 100, 1)
                })

        return stats
