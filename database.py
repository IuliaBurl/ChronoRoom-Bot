import json
import sqlite3
import threading


class Database:
    def __init__(self, db_name='chronoroom.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.lock = threading.RLock()
        self.create_tables()

    def create_tables(self):
        with self.lock, self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    test_answers TEXT,
                    test_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS match_queue (
                    user_id INTEGER PRIMARY KEY,
                    test_type TEXT,
                    looking_for_match BOOLEAN DEFAULT TRUE,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_ids TEXT,
                    test_type TEXT,
                    group_chat_id TEXT,
                    invite_link TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            self.conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_queue_type ON match_queue (test_type, joined_at)'
            )

    def save_user_test(self, user_id, username, first_name, answers, test_type):
        with self.lock, self.conn:
            self.conn.execute('''
                INSERT INTO users (user_id, username, first_name, test_answers, test_type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    test_answers = excluded.test_answers,
                    test_type = excluded.test_type
            ''', (user_id, username, first_name, json.dumps(answers), test_type))

    def add_to_match_queue(self, user_id, test_type):
        with self.lock, self.conn:
            self.conn.execute('''
                INSERT OR REPLACE INTO match_queue (user_id, test_type, looking_for_match)
                VALUES (?, ?, TRUE)
            ''', (user_id, test_type))

    def get_users_in_queue_by_type(self, test_type):
        with self.lock:
            cursor = self.conn.execute('''
                SELECT u.user_id, u.username, u.first_name, u.test_answers
                FROM match_queue mq
                JOIN users u ON mq.user_id = u.user_id
                WHERE mq.looking_for_match = TRUE AND mq.test_type = ?
                ORDER BY mq.joined_at, mq.rowid
            ''', (test_type,))
            return cursor.fetchall()

    def remove_from_queue(self, user_id):
        with self.lock, self.conn:
            self.conn.execute('DELETE FROM match_queue WHERE user_id = ?', (user_id,))

    def create_match(self, user_ids, test_type):
        with self.lock, self.conn:
            cursor = self.conn.execute('''
                INSERT INTO matches (user_ids, test_type)
                VALUES (?, ?)
            ''', (json.dumps(user_ids), test_type))
            match_id = cursor.lastrowid
            self.conn.executemany(
                'DELETE FROM match_queue WHERE user_id = ?',
                [(user_id,) for user_id in user_ids]
            )
            return match_id

    def get_user(self, user_id):
        with self.lock:
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
