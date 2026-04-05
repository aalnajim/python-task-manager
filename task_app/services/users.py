from __future__ import annotations

import sqlite3

from cryptography.hazmat.primitives import serialization

from task_app.data.database import Database, utc_now
from task_app.models import ROLE_ADMIN, ROLE_USER, User


class UserService:
    def __init__(self, db: Database):
        self.db = db

    def list_users(self) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, username, display_name, role, active, created_at, public_key_pem FROM users ORDER BY display_name"
            ).fetchall()
        return [
            User(
                id=row["id"],
                username=row["username"],
                display_name=row["display_name"],
                role=row["role"],
                active=bool(row["active"]),
                created_at=row["created_at"],
                public_key_pem=row["public_key_pem"],
            )
            for row in rows
        ]

    def list_admin_users(self) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, display_name, role, active, created_at, public_key_pem
                FROM users
                WHERE role = 'admin' AND active = 1
                ORDER BY display_name
                """
            ).fetchall()
        return [
            User(
                id=row["id"],
                username=row["username"],
                display_name=row["display_name"],
                role=row["role"],
                active=bool(row["active"]),
                created_at=row["created_at"],
                public_key_pem=row["public_key_pem"],
            )
            for row in rows
        ]

    def create_user(self, username: str, display_name: str, password: str, role: str = ROLE_USER) -> None:
        if role not in {ROLE_ADMIN, ROLE_USER}:
            raise ValueError("Invalid role.")
        if not username.strip() or not display_name.strip() or not password:
            raise ValueError("Username, display name, and password are required.")
        with self.db.connect() as conn:
            public_key_pem, encrypted_private_key = self.db.security.generate_user_keypair(password)
            conn.execute(
                """
                INSERT INTO users (username, display_name, password_hash, public_key_pem, encrypted_private_key, role, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    username.strip(),
                    display_name.strip(),
                    self.db.security.hash_password(password),
                    public_key_pem,
                    encrypted_private_key,
                    role,
                    utc_now(),
                ),
            )

    def set_user_active(self, user_id: int, active: bool) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))

    def get_user(self, user_id: int) -> User:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, display_name, role, active, created_at, public_key_pem
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if not row:
            raise ValueError("User not found.")
        return User(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            public_key_pem=row["public_key_pem"],
        )

    def update_profile(
        self,
        user_id: int,
        username: str,
        display_name: str,
        current_password: str,
        new_password: str = "",
    ) -> User:
        if not username.strip() or not display_name.strip():
            raise ValueError("Username and display name are required.")
        if not current_password:
            raise ValueError("Current password is required.")
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT password_hash, encrypted_private_key FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                raise ValueError("User not found.")
            if not self.db.security.verify_password(current_password, row["password_hash"]):
                raise ValueError("Current password is incorrect.")
            password_hash = self.db.security.hash_password(new_password) if new_password else row["password_hash"]
            encrypted_private_key = row["encrypted_private_key"]
            if new_password:
                private_key = self.db.security.load_private_key(encrypted_private_key, current_password)
                encrypted_private_key = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(new_password.encode("utf-8")),
                ).decode("utf-8")
            session_private_key = self.db.security.load_private_key(
                encrypted_private_key,
                new_password or current_password,
            )
            try:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, display_name = ?, password_hash = ?, encrypted_private_key = ?
                    WHERE id = ?
                    """,
                    (username.strip(), display_name.strip(), password_hash, encrypted_private_key, user_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("That username is already in use.") from exc
        user = self.get_user(user_id)
        user.session_private_key = session_private_key
        return user
