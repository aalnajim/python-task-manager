from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


STATUS_NEW = "new"
STATUS_IN_PROGRESS = "under_progress"
STATUS_COMPLETED = "completed"
TASK_STATUSES = [STATUS_NEW, STATUS_IN_PROGRESS, STATUS_COMPLETED]

PRIORITIES = ["low", "medium", "high", "critical"]

ROLE_ADMIN = "admin"
ROLE_USER = "user"


@dataclass(slots=True)
class User:
    id: int
    username: str
    display_name: str
    role: str
    active: bool
    created_at: str
    public_key_pem: str | None = None
    session_private_key: Any | None = field(default=None, repr=False)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


@dataclass(slots=True)
class Attachment:
    id: int
    task_id: int
    original_name: str
    stored_path: str
    mime_type: str
    file_size: int
    added_by_user_id: int
    created_at: str


@dataclass(slots=True)
class Task:
    id: int
    title: str
    description: str
    priority: str
    status: str
    deadline: str | None
    more_info: str
    creator_user_id: int
    creator_name: str
    assigned_user_id: int | None
    assigned_name: str | None
    created_at: str
    updated_at: str

    @property
    def deadline_dt(self) -> datetime | None:
        if not self.deadline:
            return None
        try:
            return datetime.fromisoformat(self.deadline)
        except ValueError:
            return None

    @property
    def is_overdue(self) -> bool:
        deadline = self.deadline_dt
        return bool(deadline and deadline < datetime.now() and self.status != STATUS_COMPLETED)


@dataclass(slots=True)
class TaskHistoryEntry:
    id: int
    task_id: int
    action: str
    actor_user_id: int
    actor_name: str
    details: str
    timestamp: str
