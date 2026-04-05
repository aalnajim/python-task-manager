from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet

from task_app.models import (
    ALL_PERMISSIONS,
    PERMISSION_ASSIGN_TASKS,
    PERMISSION_CREATE_TASKS,
    PERMISSION_DELETE_ALL_TASKS,
    PERMISSION_DELETE_OWN_TASKS,
    PERMISSION_EDIT_ALL_TASKS,
    PERMISSION_EDIT_OWN_TASKS,
    PERMISSION_EXPORT_DATA,
    PERMISSION_IMPORT_DATA,
    PERMISSION_MANAGE_ROLES,
    PERMISSION_MANAGE_USERS,
    PERMISSION_UPDATE_ALL_TASK_STATUS,
    PERMISSION_UPDATE_OWN_TASK_STATUS,
    PERMISSION_VIEW_ALL_TASKS,
    ROLE_ADMIN,
    ROLE_USER,
)
from task_app.utils.security import SecurityManager


def utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


DEFAULT_ROLES = [
    {
        "name": "Administrator",
        "description": "Full access to users, roles, tasks, and data tools.",
        "permissions": ALL_PERMISSIONS,
        "legacy_role": ROLE_ADMIN,
        "is_system": 1,
    },
    {
        "name": "Staff",
        "description": "Create and manage personal tasks.",
        "permissions": [
            PERMISSION_CREATE_TASKS,
            PERMISSION_EDIT_OWN_TASKS,
            PERMISSION_DELETE_OWN_TASKS,
            PERMISSION_UPDATE_OWN_TASK_STATUS,
        ],
        "legacy_role": ROLE_USER,
        "is_system": 1,
    },
]


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
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    is_system INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS role_permissions (
                    role_id INTEGER NOT NULL,
                    permission TEXT NOT NULL,
                    PRIMARY KEY(role_id, permission),
                    FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE
                );

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
                    master_task_key TEXT,
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
            self._ensure_task_columns(conn)
            self._seed_default_roles(conn)
            self._seed_default_admin(conn)
            self._migrate_users_to_roles(conn)
            self._migrate_existing_rows(conn)

    def _ensure_user_columns(self, conn) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "public_key_pem" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN public_key_pem TEXT")
        if "encrypted_private_key" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN encrypted_private_key TEXT")
        if "role_id" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES roles(id)")

    def _ensure_task_columns(self, conn) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "master_task_key" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN master_task_key TEXT")

    def _seed_default_roles(self, conn) -> None:
        for role in DEFAULT_ROLES:
            row = conn.execute("SELECT id FROM roles WHERE name = ?", (role["name"],)).fetchone()
            if row:
                role_id = row["id"]
                conn.execute(
                    "UPDATE roles SET description = ?, is_system = ? WHERE id = ?",
                    (role["description"], role["is_system"], role_id),
                )
            else:
                cursor = conn.execute(
                    "INSERT INTO roles (name, description, is_system, created_at) VALUES (?, ?, ?, ?)",
                    (role["name"], role["description"], role["is_system"], utc_now()),
                )
                role_id = int(cursor.lastrowid)
            conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            conn.executemany(
                "INSERT INTO role_permissions (role_id, permission) VALUES (?, ?)",
                [(role_id, permission) for permission in role["permissions"]],
            )

    def _seed_default_admin(self, conn) -> None:
        exists = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if exists:
            return
        admin_role_id = self._role_id_by_legacy_name(conn, ROLE_ADMIN)
        public_key_pem, encrypted_private_key = self.security.generate_user_keypair("admin123")
        conn.execute(
            """
            INSERT INTO users (username, display_name, password_hash, public_key_pem, encrypted_private_key, role, role_id, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                "admin",
                "Administrator",
                self.security.hash_password("admin123"),
                public_key_pem,
                encrypted_private_key,
                ROLE_ADMIN,
                admin_role_id,
                utc_now(),
            ),
        )

    def _role_id_by_legacy_name(self, conn, legacy_role: str) -> int:
        role_name = "Administrator" if legacy_role == ROLE_ADMIN else "Staff"
        row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
        if not row:
            raise ValueError(f"Missing system role for {legacy_role}.")
        return int(row["id"])

    def _migrate_users_to_roles(self, conn) -> None:
        rows = conn.execute("SELECT id, role, role_id FROM users").fetchall()
        for row in rows:
            if row["role_id"]:
                continue
            legacy_role = row["role"] or ROLE_USER
            role_id = self._role_id_by_legacy_name(conn, legacy_role)
            conn.execute("UPDATE users SET role_id = ? WHERE id = ?", (role_id, row["id"]))

    def _migrate_existing_rows(self, conn) -> None:
        task_rows = conn.execute("SELECT id, title, description, deadline, more_info, master_task_key FROM tasks").fetchall()
        for row in task_rows:
            has_access = conn.execute("SELECT 1 FROM task_access WHERE task_id = ? LIMIT 1", (row["id"],)).fetchone()
            if has_access:
                continue
            task_key = Fernet.generate_key()
            conn.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, deadline = ?, more_info = ?, master_task_key = ?
                WHERE id = ?
                """,
                (
                    "task:" + Fernet(task_key).encrypt((self.security.decrypt_text(row["title"]) or "").encode("utf-8")).decode("ascii"),
                    "task:" + Fernet(task_key).encrypt((self.security.decrypt_text(row["description"]) or "").encode("utf-8")).decode("ascii"),
                    "task:" + Fernet(task_key).encrypt(self.security.decrypt_text(row["deadline"]).encode("utf-8")).decode("ascii")
                    if row["deadline"]
                    else None,
                    "task:" + Fernet(task_key).encrypt((self.security.decrypt_text(row["more_info"]) or "").encode("utf-8")).decode("ascii"),
                    self.security.encrypt_text(task_key.decode("ascii")),
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
