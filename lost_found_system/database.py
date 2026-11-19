"""
database.py - SQLite Database Manager for Lost & Found System
"""
import sqlite3
import os
from models import Item
from typing import List, Optional

DB_NAME = "lost_found.db"

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()

class DatabaseManager:
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initializes the database tables if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    location TEXT NOT NULL,
                    date_reported TEXT NOT NULL,
                    reporter_name TEXT NOT NULL,
                    reporter_contact TEXT NOT NULL,
                    status TEXT DEFAULT 'Open',
                    reward TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            columns = {row['name'] for row in cursor.execute('PRAGMA table_info(items)')}
            if 'user_id' not in columns:
                cursor.execute('ALTER TABLE items ADD COLUMN user_id INTEGER REFERENCES users(id)')
            if 'photo' not in columns:
                cursor.execute('ALTER TABLE items ADD COLUMN photo BLOB')
            if 'photo_type' not in columns:
                cursor.execute('ALTER TABLE items ADD COLUMN photo_type TEXT')
            cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'admin'))
            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL REFERENCES items(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.commit()

    def add_item(self, item: Item) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO items (title, category, item_type, description, location, date_reported, reporter_name, reporter_contact, status, reward, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.title, item.category, item.item_type, item.description,
                item.location, item.date_reported, item.reporter_name,
                item.reporter_contact, item.status, item.reward, item.created_at
            ))
            conn.commit()
            return cursor.lastrowid

    def get_all_items(self, item_type: Optional[str] = None) -> List[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if item_type:
                cursor.execute("SELECT * FROM items WHERE item_type = ? ORDER BY id DESC", (item_type,))
            else:
                cursor.execute("SELECT * FROM items ORDER BY id DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_item_by_id(self, item_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_status(self, item_id: int, status: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_item(self, item_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0
