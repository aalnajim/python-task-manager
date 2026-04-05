from __future__ import annotations

import base64
import mimetypes
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet

from task_app.data.database import Database, utc_now
from task_app.models import PRIORITIES, STATUS_COMPLETED, TASK_STATUSES, Attachment, Task, TaskHistoryEntry, User


class PermissionError(Exception):
    pass


class TaskService:
    def __init__(self, db: Database, attachments_dir: Path):
        self.db = db
        self.attachments_dir = attachments_dir

    def list_tasks(
        self,
        current_user: User,
        query: str = "",
        status: str = "",
        priority: str = "",
        owner_id: int | None = None,
        assignee_id: int | None = None,
        include_all: bool = True,
    ) -> list[Task]:
        self._migrate_legacy_tasks()
        clauses = []
        params: list[object] = []
        if not current_user.is_admin and not include_all:
            clauses.append("(t.creator_user_id = ? OR t.assigned_user_id = ?)")
            params.extend([current_user.id, current_user.id])
        if status:
            clauses.append("t.status = ?")
            params.append(status)
        if priority:
            clauses.append("t.priority = ?")
            params.append(priority)
        if owner_id:
            clauses.append("t.creator_user_id = ?")
            params.append(owner_id)
        if assignee_id is not None:
            if assignee_id == -1:
                clauses.append("t.assigned_user_id IS NULL")
            else:
                clauses.append("t.assigned_user_id = ?")
                params.append(assignee_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    t.*,
                    creator.display_name AS creator_name,
                    assignee.display_name AS assigned_name
                FROM tasks t
                JOIN users creator ON creator.id = t.creator_user_id
                LEFT JOIN users assignee ON assignee.id = t.assigned_user_id
                {where}
                ORDER BY t.updated_at DESC
                """,
                params,
            ).fetchall()
        tasks: list[Task] = []
        for row in rows:
            try:
                tasks.append(self._row_to_task(current_user, row))
            except PermissionError:
                continue
        if query:
            search = query.lower()
            tasks = [
                task
                for task in tasks
                if search in task.title.lower() or search in task.description.lower() or search in task.more_info.lower()
            ]
        return sorted(tasks, key=lambda task: (task.deadline_dt is None, task.deadline_dt or datetime.max, task.updated_at))

    def get_task(self, current_user: User, task_id: int) -> Task:
        self._migrate_legacy_tasks()
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    t.*,
                    creator.display_name AS creator_name,
                    assignee.display_name AS assigned_name
                FROM tasks t
                JOIN users creator ON creator.id = t.creator_user_id
                LEFT JOIN users assignee ON assignee.id = t.assigned_user_id
                WHERE t.id = ?
                """,
                (task_id,),
            ).fetchone()
        if not row:
            raise ValueError("Task not found.")
        return self._row_to_task(current_user, row)

    def list_attachments(self, task_id: int) -> list[Attachment]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM attachments WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
        return [
            Attachment(
                id=row["id"],
                task_id=row["task_id"],
                original_name=row["original_name"],
                stored_path=row["stored_path"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                added_by_user_id=row["added_by_user_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def remove_attachment(self, current_user: User, attachment_id: int) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT a.*, t.creator_user_id, t.assigned_user_id
                FROM attachments a
                JOIN tasks t ON t.id = a.task_id
                WHERE a.id = ?
                """,
                (attachment_id,),
            ).fetchone()
        if not row:
            raise ValueError("Attachment not found.")
        task = self.get_task(current_user, row["task_id"])
        if not self.can_edit(current_user, task):
            raise PermissionError("You cannot remove attachments from this task.")
        task_key = self._get_task_key(task.id, current_user)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
            self._add_history_with_key(
                conn,
                task.id,
                task_key,
                "attachment_removed",
                current_user.id,
                f"Removed attachment {row['original_name']}",
            )
        path = Path(row["stored_path"])
        if path.exists():
            path.unlink()

    def list_history(self, current_user: User, task_id: int) -> list[TaskHistoryEntry]:
        task_key = self._get_task_key(task_id, current_user)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT h.*, u.display_name AS actor_name
                FROM task_history h
                JOIN users u ON u.id = h.actor_user_id
                WHERE task_id = ?
                ORDER BY timestamp DESC
                """,
                (task_id,),
            ).fetchall()
        return [
            TaskHistoryEntry(
                id=row["id"],
                task_id=row["task_id"],
                action=row["action"],
                actor_user_id=row["actor_user_id"],
                actor_name=row["actor_name"],
                details=self._decrypt_field(task_key, row["details"]) or "",
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def create_task(
        self,
        current_user: User,
        title: str,
        description: str,
        priority: str,
        deadline: str | None,
        more_info: str,
        assigned_user_id: int | None,
        attachment_paths: list[str],
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> int:
        if priority not in PRIORITIES:
            raise ValueError("Invalid priority.")
        if not title.strip():
            raise ValueError("Title is required.")
        if assigned_user_id and not current_user.is_admin:
            raise PermissionError("Only admin can assign a task during creation.")
        task_key = Fernet.generate_key()
        created_ts = created_at or utc_now()
        updated_ts = updated_at or created_ts
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    title, description, priority, status, deadline, more_info,
                    creator_user_id, assigned_user_id, created_at, updated_at
                )
                VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._encrypt_field(task_key, title.strip()),
                    self._encrypt_field(task_key, description.strip()),
                    priority,
                    self._encrypt_field(task_key, deadline) if deadline else None,
                    self._encrypt_field(task_key, more_info.strip()),
                    current_user.id,
                    assigned_user_id,
                    created_ts,
                    updated_ts,
                ),
            )
            task_id = int(cursor.lastrowid)
            self._grant_access(conn, task_id, task_key, current_user.id, assigned_user_id)
            self._add_history_with_key(conn, task_id, task_key, "created", current_user.id, f"Task created by {current_user.display_name}", created_ts)
            if assigned_user_id:
                self._add_history_with_key(conn, task_id, task_key, "assigned", current_user.id, f"Assigned during creation to user #{assigned_user_id}", created_ts)
            self._store_attachments(conn, task_id, current_user.id, attachment_paths, task_key)
        return task_id

    def update_task(
        self,
        current_user: User,
        task_id: int,
        title: str,
        description: str,
        priority: str,
        status: str,
        deadline: str | None,
        more_info: str,
        assigned_user_id: int | None,
        attachment_paths: list[str],
    ) -> None:
        if priority not in PRIORITIES or status not in TASK_STATUSES:
            raise ValueError("Invalid task values.")
        task = self.get_task(current_user, task_id)
        if not self.can_edit(current_user, task):
            raise PermissionError("You cannot edit this task.")
        if assigned_user_id != task.assigned_user_id and not current_user.is_admin:
            raise PermissionError("Only admin can assign or reassign tasks.")
        task_key = self._get_task_key(task_id, current_user)
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, priority = ?, status = ?, deadline = ?, more_info = ?,
                    assigned_user_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    self._encrypt_field(task_key, title.strip()),
                    self._encrypt_field(task_key, description.strip()),
                    priority,
                    status,
                    self._encrypt_field(task_key, deadline) if deadline else None,
                    self._encrypt_field(task_key, more_info.strip()),
                    assigned_user_id,
                    utc_now(),
                    task_id,
                ),
            )
            self._grant_access(conn, task_id, task_key, task.creator_user_id, assigned_user_id)
            self._add_history_with_key(conn, task_id, task_key, "updated", current_user.id, f"Task updated by {current_user.display_name}")
            if assigned_user_id != task.assigned_user_id:
                action = "reassigned" if task.assigned_user_id else "assigned"
                self._add_history_with_key(conn, task_id, task_key, action, current_user.id, f"Assignee changed to {assigned_user_id or 'unassigned'}")
            self._store_attachments(conn, task_id, current_user.id, attachment_paths, task_key)

    def change_status(self, current_user: User, task_id: int, status: str) -> None:
        if status not in TASK_STATUSES:
            raise ValueError("Invalid status.")
        task = self.get_task(current_user, task_id)
        if not self.can_change_status(current_user, task):
            raise PermissionError("You cannot update this task status.")
        task_key = self._get_task_key(task_id, current_user)
        with self.db.connect() as conn:
            conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, utc_now(), task_id))
            self._add_history_with_key(conn, task_id, task_key, "status_changed", current_user.id, f"Status changed to {status}")

    def delete_task(self, current_user: User, task_id: int) -> None:
        task = self.get_task(current_user, task_id)
        if not self.can_delete(current_user, task):
            raise PermissionError("You cannot delete this task.")
        attachments = self.list_attachments(task_id)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        for attachment in attachments:
            path = Path(attachment.stored_path)
            if path.exists():
                path.unlink()

    def can_edit(self, current_user: User, task: Task) -> bool:
        return current_user.is_admin or task.creator_user_id == current_user.id

    def can_delete(self, current_user: User, task: Task) -> bool:
        if current_user.is_admin:
            return True
        return task.creator_user_id == current_user.id and task.assigned_user_id is None

    def can_change_status(self, current_user: User, task: Task) -> bool:
        if current_user.is_admin:
            return True
        return current_user.id in {task.creator_user_id, task.assigned_user_id}

    def stats_for(self, current_user: User) -> dict[str, int]:
        tasks = self.list_tasks(current_user, include_all=False)
        overdue = sum(1 for task in tasks if task.is_overdue)
        due_today = sum(1 for task in tasks if task.deadline_dt and task.deadline_dt.date() == datetime.now().date())
        completed = sum(1 for task in tasks if task.status == STATUS_COMPLETED)
        return {"total": len(tasks), "overdue": overdue, "due_today": due_today, "completed": completed}

    def import_task_bundle(
        self,
        current_user: User,
        task_data: dict[str, object],
        creator_user_id: int,
        assigned_user_id: int | None,
        attachments: list[dict[str, object]],
        history: list[dict[str, object]],
        attachment_root: Path,
    ) -> int:
        task_key = Fernet.generate_key()
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    title, description, priority, status, deadline, more_info,
                    creator_user_id, assigned_user_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._encrypt_field(task_key, str(task_data["title"])),
                    self._encrypt_field(task_key, str(task_data["description"])),
                    str(task_data["priority"]),
                    str(task_data["status"]),
                    self._encrypt_field(task_key, str(task_data["deadline"])) if task_data["deadline"] else None,
                    self._encrypt_field(task_key, str(task_data["more_info"])),
                    creator_user_id,
                    assigned_user_id,
                    str(task_data["created_at"]),
                    str(task_data["updated_at"]),
                ),
            )
            task_id = int(cursor.lastrowid)
            self._grant_access(conn, task_id, task_key, creator_user_id, assigned_user_id)
            for attachment in attachments:
                source = attachment_root / str(attachment["archive_name"])
                if source.exists():
                    dest = self.attachments_dir / source.name
                    shutil.copy2(source, dest)
                    conn.execute(
                        """
                        INSERT INTO attachments (
                            task_id, original_name, stored_path, mime_type, file_size, added_by_user_id, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            str(attachment["original_name"]),
                            str(dest),
                            str(attachment["mime_type"]),
                            int(attachment["file_size"]),
                            current_user.id,
                            str(attachment["created_at"]),
                        ),
                    )
            for entry in history:
                self._add_history_with_key(
                    conn,
                    task_id,
                    task_key,
                    str(entry["action"]),
                    current_user.id,
                    str(entry["details"]),
                    str(entry["timestamp"]),
                )
        return task_id

    def _store_attachments(self, conn, task_id: int, actor_user_id: int, attachment_paths: list[str], task_key: bytes) -> None:
        for path_str in attachment_paths:
            source = Path(path_str)
            if not source.exists():
                continue
            unique_name = f"{uuid.uuid4().hex}_{source.name}"
            dest = self.attachments_dir / unique_name
            shutil.copy2(source, dest)
            mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            conn.execute(
                """
                INSERT INTO attachments (
                    task_id, original_name, stored_path, mime_type, file_size, added_by_user_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, source.name, str(dest), mime_type, source.stat().st_size, actor_user_id, utc_now()),
            )
            self._add_history_with_key(conn, task_id, task_key, "attachment_added", actor_user_id, f"Added attachment {source.name}")

    def _add_history_with_key(
        self, conn, task_id: int, task_key: bytes, action: str, actor_user_id: int, details: str, timestamp: str | None = None
    ) -> None:
        conn.execute(
            """
            INSERT INTO task_history (task_id, action, actor_user_id, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, action, actor_user_id, self._encrypt_field(task_key, details), timestamp or utc_now()),
        )

    def _row_to_task(self, current_user: User, row) -> Task:
        task_key = self._get_task_key(row["id"], current_user)
        return Task(
            id=row["id"],
            title=self._decrypt_field(task_key, row["title"]) or "",
            description=self._decrypt_field(task_key, row["description"]) or "",
            priority=row["priority"],
            status=row["status"],
            deadline=self._decrypt_field(task_key, row["deadline"]),
            more_info=self._decrypt_field(task_key, row["more_info"]) or "",
            creator_user_id=row["creator_user_id"],
            creator_name=row["creator_name"],
            assigned_user_id=row["assigned_user_id"],
            assigned_name=row["assigned_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _get_task_key(self, task_id: int, current_user: User) -> bytes:
        if current_user.session_private_key is None:
            raise PermissionError("This session cannot decrypt task data.")
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT encrypted_task_key FROM task_access WHERE task_id = ? AND user_id = ?",
                (task_id, current_user.id),
            ).fetchone()
        if not row:
            raise PermissionError("You do not have access to decrypt this task.")
        return self.db.security.decrypt_task_key_for_user(row["encrypted_task_key"], current_user.session_private_key)

    def _grant_access(self, conn, task_id: int, task_key: bytes, creator_user_id: int, assigned_user_id: int | None) -> None:
        user_rows = conn.execute(
            """
            SELECT id, public_key_pem, role, active
            FROM users
            WHERE active = 1 AND (id = ? OR id = ? OR role = 'admin')
            """,
            (creator_user_id, assigned_user_id),
        ).fetchall()
        for user in user_rows:
            if not user["public_key_pem"]:
                continue
            encrypted_task_key = self.db.security.encrypt_task_key_for_user(task_key, user["public_key_pem"])
            conn.execute(
                """
                INSERT INTO task_access (task_id, user_id, encrypted_task_key)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id, user_id) DO UPDATE SET encrypted_task_key = excluded.encrypted_task_key
                """,
                (task_id, user["id"], encrypted_task_key),
            )

    def _encrypt_field(self, task_key: bytes, value: str | None) -> str | None:
        if value is None:
            return None
        return "task:" + Fernet(task_key).encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt_field(self, task_key: bytes, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("task:"):
            token = value.split("task:", 1)[1]
            return Fernet(task_key).decrypt(token.encode("ascii")).decode("utf-8")
        plain = self.db.security.decrypt_text(value)
        if plain and plain.startswith("task:"):
            token = plain.split("task:", 1)[1]
            return Fernet(task_key).decrypt(token.encode("ascii")).decode("utf-8")
        return plain

    def _migrate_legacy_tasks(self) -> None:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, title, description, deadline, more_info, creator_user_id, assigned_user_id FROM tasks"
            ).fetchall()
            for row in rows:
                has_access = conn.execute("SELECT 1 FROM task_access WHERE task_id = ? LIMIT 1", (row["id"],)).fetchone()
                if has_access:
                    continue
                task_key = Fernet.generate_key()
                conn.execute(
                    """
                    UPDATE tasks
                    SET title = ?, description = ?, deadline = ?, more_info = ?
                    WHERE id = ?
                    """,
                    (
                        self._encrypt_field(task_key, self.db.security.decrypt_text(row["title"]) or ""),
                        self._encrypt_field(task_key, self.db.security.decrypt_text(row["description"]) or ""),
                        self._encrypt_field(task_key, self.db.security.decrypt_text(row["deadline"])) if row["deadline"] else None,
                        self._encrypt_field(task_key, self.db.security.decrypt_text(row["more_info"]) or ""),
                        row["id"],
                    ),
                )
                self._grant_access(conn, row["id"], task_key, row["creator_user_id"], row["assigned_user_id"])
                history_rows = conn.execute("SELECT id, details FROM task_history WHERE task_id = ?", (row["id"],)).fetchall()
                for history in history_rows:
                    plain_details = self.db.security.decrypt_text(history["details"]) or ""
                    conn.execute(
                        "UPDATE task_history SET details = ? WHERE id = ?",
                        (self._encrypt_field(task_key, plain_details), history["id"]),
                    )
