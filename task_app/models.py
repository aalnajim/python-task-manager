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

PERMISSION_MANAGE_USERS = "manage_users"
PERMISSION_MANAGE_ROLES = "manage_roles"
PERMISSION_VIEW_ALL_TASKS = "view_all_tasks"
PERMISSION_CREATE_TASKS = "create_tasks"
PERMISSION_EDIT_OWN_TASKS = "edit_own_tasks"
PERMISSION_EDIT_ALL_TASKS = "edit_all_tasks"
PERMISSION_DELETE_OWN_TASKS = "delete_own_tasks"
PERMISSION_DELETE_ALL_TASKS = "delete_all_tasks"
PERMISSION_ASSIGN_TASKS = "assign_tasks"
PERMISSION_UPDATE_OWN_TASK_STATUS = "update_own_task_status"
PERMISSION_UPDATE_ALL_TASK_STATUS = "update_all_task_status"
PERMISSION_EXPORT_DATA = "export_data"
PERMISSION_IMPORT_DATA = "import_data"

ALL_PERMISSIONS = [
    PERMISSION_MANAGE_USERS,
    PERMISSION_MANAGE_ROLES,
    PERMISSION_VIEW_ALL_TASKS,
    PERMISSION_CREATE_TASKS,
    PERMISSION_EDIT_OWN_TASKS,
    PERMISSION_EDIT_ALL_TASKS,
    PERMISSION_DELETE_OWN_TASKS,
    PERMISSION_DELETE_ALL_TASKS,
    PERMISSION_ASSIGN_TASKS,
    PERMISSION_UPDATE_OWN_TASK_STATUS,
    PERMISSION_UPDATE_ALL_TASK_STATUS,
    PERMISSION_EXPORT_DATA,
    PERMISSION_IMPORT_DATA,
]

PERMISSION_LABELS = {
    PERMISSION_MANAGE_USERS: "Manage users",
    PERMISSION_MANAGE_ROLES: "Manage roles",
    PERMISSION_VIEW_ALL_TASKS: "View all tasks",
    PERMISSION_CREATE_TASKS: "Create tasks",
    PERMISSION_EDIT_OWN_TASKS: "Edit own tasks",
    PERMISSION_EDIT_ALL_TASKS: "Edit all tasks",
    PERMISSION_DELETE_OWN_TASKS: "Delete own tasks",
    PERMISSION_DELETE_ALL_TASKS: "Delete all tasks",
    PERMISSION_ASSIGN_TASKS: "Assign tasks",
    PERMISSION_UPDATE_OWN_TASK_STATUS: "Update own task status",
    PERMISSION_UPDATE_ALL_TASK_STATUS: "Update all task status",
    PERMISSION_EXPORT_DATA: "Export data",
    PERMISSION_IMPORT_DATA: "Import data",
}


@dataclass(slots=True)
class Role:
    id: int
    name: str
    description: str
    permissions: tuple[str, ...]
    is_system: bool
    created_at: str

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass(slots=True)
class User:
    id: int
    username: str
    display_name: str
    role_id: int
    role: str
    active: bool
    created_at: str
    public_key_pem: str | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    session_private_key: Any | None = field(default=None, repr=False)

    @property
    def is_admin(self) -> bool:
        return self.has_permission(PERMISSION_MANAGE_USERS) and self.has_permission(PERMISSION_MANAGE_ROLES)

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


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
