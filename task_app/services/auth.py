from __future__ import annotations

from task_app.data.database import Database
from task_app.models import User


class AuthService:
    def __init__(self, db: Database):
        self.db = db

    def login(self, username: str, password: str) -> User | None:
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
                    u.must_change_password,
                    u.is_bootstrap_admin,
                    u.created_at,
                    u.password_hash,
                    u.public_key_pem,
                    u.encrypted_private_key,
                    GROUP_CONCAT(rp.permission) AS permissions
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                WHERE username = ?
                GROUP BY u.id
                """,
                (username.strip(),),
            ).fetchone()
        if not row or not row["active"]:
            return None
        if not self.db.security.verify_password(password, row["password_hash"]):
            return None
        if self.db.security.needs_password_upgrade(row["password_hash"]):
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (self.db.security.hash_password(password), row["id"]),
                )
        public_key_pem = row["public_key_pem"]
        encrypted_private_key = row["encrypted_private_key"]
        if not public_key_pem or not encrypted_private_key:
            public_key_pem, encrypted_private_key = self.db.security.generate_user_keypair(password)
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE users SET public_key_pem = ?, encrypted_private_key = ? WHERE id = ?",
                    (public_key_pem, encrypted_private_key, row["id"]),
                )
        private_key = self.db.security.load_private_key(encrypted_private_key, password)
        return User(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role_id=row["role_id"],
            role=row["role_name"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            public_key_pem=public_key_pem,
            permissions=frozenset(filter(None, (row["permissions"] or "").split(","))),
            must_change_password=bool(row["must_change_password"]),
            is_bootstrap_admin=bool(row["is_bootstrap_admin"]),
            session_private_key=private_key,
        )
