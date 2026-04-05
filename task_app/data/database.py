from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from task_app.utils.security import SecurityManager


def utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, db_path: Path, security: SecurityManager):
        self.db_path = db_path
        self.security = security

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    public_key_pem TEXT,
                    encrypted_private_key TEXT,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    deadline TEXT,
                    more_info TEXT NOT NULL DEFAULT '',
                    creator_user_id INTEGER NOT NULL,
                    assigned_user_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(creator_user_id) REFERENCES users(id),
                    FOREIGN KEY(assigned_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    added_by_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(added_by_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor_user_id INTEGER NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(actor_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS task_access (
                    task_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    encrypted_task_key TEXT NOT NULL,
                    PRIMARY KEY(task_id, user_id),
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )
            self._ensure_user_columns(conn)
            exists = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
            if not exists:
                public_key_pem, encrypted_private_key = self.security.generate_user_keypair("admin123")
                conn.execute(
                    """
                    INSERT INTO users (username, display_name, password_hash, public_key_pem, encrypted_private_key, role, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        "admin",
                        "Administrator",
                        self.security.hash_password("admin123"),
                        public_key_pem,
                        encrypted_private_key,
                        "admin",
                        utc_now(),
                    ),
                )
            self._migrate_existing_rows(conn)

    def _ensure_user_columns(self, conn) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "public_key_pem" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN public_key_pem TEXT")
        if "encrypted_private_key" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN encrypted_private_key TEXT")

    def _migrate_existing_rows(self, conn) -> None:
        task_rows = conn.execute("SELECT id, title, description, deadline, more_info FROM tasks").fetchall()
        for row in task_rows:
            has_access = conn.execute("SELECT 1 FROM task_access WHERE task_id = ? LIMIT 1", (row["id"],)).fetchone()
            if has_access:
                continue
            conn.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, deadline = ?, more_info = ?
                WHERE id = ?
                """,
                (
                    self.security.encrypt_text(self.security.decrypt_text(row["title"]) or ""),
                    self.security.encrypt_text(self.security.decrypt_text(row["description"]) or ""),
                    self.security.encrypt_text(self.security.decrypt_text(row["deadline"])) if row["deadline"] else None,
                    self.security.encrypt_text(self.security.decrypt_text(row["more_info"]) or ""),
                    row["id"],
                ),
            )

        history_rows = conn.execute("SELECT id, details FROM task_history").fetchall()
        for row in history_rows:
            if (row["details"] or "").startswith("task:"):
                continue
            conn.execute(
                "UPDATE task_history SET details = ? WHERE id = ?",
                (self.security.encrypt_text(self.security.decrypt_text(row["details"]) or ""), row["id"]),
            )
