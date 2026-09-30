import sqlite3
import json
from datetime import datetime

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('chronoroom.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        self.conn.execute('DROP TABLE IF EXISTS users')
        self.conn.execute('DROP TABLE IF EXISTS match_queue')
        self.conn.execute('DROP TABLE IF EXISTS matches')
        self.conn.execute('''
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                test_answers TEXT,
                test_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.conn.execute('''
            CREATE TABLE match_queue (
                user_id INTEGER PRIMARY KEY,
                test_type TEXT,
                looking_for_match BOOLEAN DEFAULT TRUE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.conn.execute('''
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_ids TEXT,
                test_type TEXT,
                group_chat_id TEXT,
                invite_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')

        self.conn.commit()

    def save_user_test(self, user_id, username, first_name, answers, test_type):
        self.conn.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, test_answers, test_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, json.dumps(answers), test_type))
        self.conn.commit()

    def add_to_match_queue(self, user_id, test_type):
        self.conn.execute('''
            INSERT OR REPLACE INTO match_queue (user_id, test_type, looking_for_match)
            VALUES (?, ?, TRUE)
        ''', (user_id, test_type))
        self.conn.commit()

    def get_users_in_queue_by_type(self, test_type):
        cursor = self.conn.execute('''
            SELECT u.user_id, u.username, u.first_name, u.test_answers
            FROM match_queue mq
            JOIN users u ON mq.user_id = u.user_id
            WHERE mq.looking_for_match = TRUE AND mq.test_type = ?
            ORDER BY mq.joined_at
        ''', (test_type,))
        return cursor.fetchall()

    def remove_from_queue(self, user_id):
        self.conn.execute('DELETE FROM match_queue WHERE user_id = ?', (user_id,))
        self.conn.commit()

    def create_match(self, user_ids, test_type):
        cursor = self.conn.execute('''
            INSERT INTO matches (user_ids, test_type)
            VALUES (?, ?)
            RETURNING match_id
        ''', (json.dumps(user_ids), test_type))
        match_id = cursor.fetchone()[0]
        self.conn.commit()
        return match_id

    def get_user(self, user_id):
        cursor = self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            return {
                'user_id': result[0],
                'username': result[1],
                'first_name': result[2],
                'test_answers': result[3],
                'test_type': result[4],
                'created_at': result[5]
            }
        return None
