from __future__ import annotations

import sqlite3

from cryptography.hazmat.primitives import serialization

from task_app.data.database import Database, utc_now
from task_app.models import ALL_PERMISSIONS, ROLE_USER, Role, User


class UserService:
    def __init__(self, db: Database):
        self.db = db

    def list_roles(self) -> list[Role]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    r.id,
                    r.name,
                    r.description,
                    r.is_system,
                    r.created_at,
                    GROUP_CONCAT(rp.permission) AS permissions
                FROM roles r
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                GROUP BY r.id
                ORDER BY r.is_system DESC, r.name
                """
            ).fetchall()
        return [self._row_to_role(row) for row in rows]

    def get_role(self, role_id: int) -> Role:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    r.id,
                    r.name,
                    r.description,
                    r.is_system,
                    r.created_at,
                    GROUP_CONCAT(rp.permission) AS permissions
                FROM roles r
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                WHERE r.id = ?
                GROUP BY r.id
                """,
                (role_id,),
            ).fetchone()
        if not row:
            raise ValueError("Role not found.")
        return self._row_to_role(row)

    def create_role(self, name: str, description: str, permissions: list[str]) -> Role:
        cleaned_permissions = self._validate_permissions(permissions)
        if not name.strip():
            raise ValueError("Role name is required.")
        with self.db.connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO roles (name, description, is_system, created_at) VALUES (?, ?, 0, ?)",
                    (name.strip(), description.strip(), utc_now()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A role with that name already exists.") from exc
            role_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO role_permissions (role_id, permission) VALUES (?, ?)",
                [(role_id, permission) for permission in cleaned_permissions],
            )
        return self.get_role(role_id)

    def update_role(self, role_id: int, name: str, description: str, permissions: list[str]) -> Role:
        cleaned_permissions = self._validate_permissions(permissions)
        if not name.strip():
            raise ValueError("Role name is required.")
        with self.db.connect() as conn:
            existing = conn.execute("SELECT is_system FROM roles WHERE id = ?", (role_id,)).fetchone()
            if not existing:
                raise ValueError("Role not found.")
            try:
                conn.execute(
                    "UPDATE roles SET name = ?, description = ? WHERE id = ?",
                    (name.strip(), description.strip(), role_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A role with that name already exists.") from exc
            conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            conn.executemany(
                "INSERT INTO role_permissions (role_id, permission) VALUES (?, ?)",
                [(role_id, permission) for permission in cleaned_permissions],
            )
        return self.get_role(role_id)

    def list_users(self) -> list[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.display_name,
                    u.role_id,
                    r.name AS role_name,
                    u.active,
                    u.created_at,
                    u.public_key_pem,
                    GROUP_CONCAT(rp.permission) AS permissions
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                GROUP BY u.id
                ORDER BY u.display_name
                """
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def users_with_permission(self, permission: str) -> list[User]:
        return [user for user in self.list_users() if user.active and user.has_permission(permission)]

    def create_user(self, username: str, display_name: str, password: str, role_id: int) -> None:
        if not username.strip() or not display_name.strip() or not password:
            raise ValueError("Username, display name, and password are required.")
        self.get_role(role_id)
        with self.db.connect() as conn:
            public_key_pem, encrypted_private_key = self.db.security.generate_user_keypair(password)
            try:
                conn.execute(
                    """
                    INSERT INTO users (
                        username, display_name, password_hash, public_key_pem, encrypted_private_key,
                        role, role_id, active, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        username.strip(),
                        display_name.strip(),
                        self.db.security.hash_password(password),
                        public_key_pem,
                        encrypted_private_key,
                        ROLE_USER,
                        role_id,
                        utc_now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("That username is already in use.") from exc

    def set_user_active(self, user_id: int, active: bool) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))

    def update_user_role(self, user_id: int, role_id: int) -> None:
        self.get_role(role_id)
        with self.db.connect() as conn:
            conn.execute("UPDATE users SET role_id = ? WHERE id = ?", (role_id, user_id))

    def get_user(self, user_id: int) -> User:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.display_name,
                    u.role_id,
                    r.name AS role_name,
                    u.active,
                    u.created_at,
                    u.public_key_pem,
                    GROUP_CONCAT(rp.permission) AS permissions
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                WHERE u.id = ?
                GROUP BY u.id
                """,
                (user_id,),
            ).fetchone()
        if not row:
            raise ValueError("User not found.")
        return self._row_to_user(row)

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

    def _row_to_user(self, row) -> User:
        permissions = frozenset(filter(None, (row["permissions"] or "").split(",")))
        return User(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role_id=row["role_id"],
            role=row["role_name"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            public_key_pem=row["public_key_pem"],
            permissions=permissions,
        )

    def _row_to_role(self, row) -> Role:
        permissions = tuple(sorted(filter(None, (row["permissions"] or "").split(","))))
        return Role(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            permissions=permissions,
            is_system=bool(row["is_system"]),
            created_at=row["created_at"],
        )

    def _validate_permissions(self, permissions: list[str]) -> list[str]:
        cleaned = sorted({permission for permission in permissions if permission in ALL_PERMISSIONS})
        if not cleaned:
            raise ValueError("Select at least one permission for the role.")
        return cleaned
