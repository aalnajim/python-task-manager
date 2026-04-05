from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_app.data.database import Database
from task_app.models import (
    PERMISSION_ASSIGN_TASKS,
    PERMISSION_CREATE_TASKS,
    PERMISSION_DELETE_ALL_TASKS,
    PERMISSION_EXPORT_DATA,
    PERMISSION_EDIT_ALL_TASKS,
    PERMISSION_MANAGE_ROLES,
    PERMISSION_MANAGE_USERS,
    PERMISSION_UPDATE_ALL_TASK_STATUS,
    PERMISSION_VIEW_ALL_TASKS,
    STATUS_COMPLETED,
)
from task_app.services.auth import AuthService
from task_app.services.import_export import ImportExportService
from task_app.services.tasks import TaskService
from task_app.services.users import UserService
from task_app.utils.security import SecurityManager


class TaskAppServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.security = SecurityManager(root / "secret.key")
        self.db = Database(root / "test.db", self.security)
        self.db.initialize()
        self.auth = AuthService(self.db)
        self.users = UserService(self.db)
        roles = {role.name: role for role in self.users.list_roles()}
        self.staff_role = roles["Staff"]
        self.manager_role = self.users.create_role(
            "Manager",
            "Task manager role",
            [
                PERMISSION_VIEW_ALL_TASKS,
                PERMISSION_CREATE_TASKS,
                PERMISSION_EDIT_ALL_TASKS,
                PERMISSION_DELETE_ALL_TASKS,
                PERMISSION_ASSIGN_TASKS,
                PERMISSION_UPDATE_ALL_TASK_STATUS,
                PERMISSION_EXPORT_DATA,
            ],
        )
        self.users.create_user("alice", "Alice", "pw1", self.staff_role.id)
        self.users.create_user("bob", "Bob", "pw2", self.staff_role.id)
        self.users.create_user("maria", "Maria", "pw3", self.manager_role.id)
        self.task_service = TaskService(self.db, root / "attachments")
        self.task_service.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.import_export = ImportExportService(self.db, self.task_service, self.users, root / "exports")
        self.import_export.exports_dir.mkdir(parents=True, exist_ok=True)
        self.admin = self.auth.login("admin", "admin123")
        self.alice = self.auth.login("alice", "pw1")
        self.bob = self.auth.login("bob", "pw2")
        self.maria = self.auth.login("maria", "pw3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_owner_can_delete_unassigned_task(self) -> None:
        task_id = self.task_service.create_task(
            self.alice,
            "Draft proposal",
            "Description",
            "high",
            None,
            "More info",
            None,
            [],
        )
        self.task_service.delete_task(self.alice, task_id)
        with self.assertRaises(ValueError):
            self.task_service.get_task(self.alice, task_id)

    def test_owner_cannot_delete_assigned_task(self) -> None:
        task_id = self.task_service.create_task(
            self.admin,
            "Assign me",
            "Description",
            "medium",
            None,
            "",
            self.alice.id,
            [],
        )
        with self.assertRaises(Exception):
            self.task_service.delete_task(self.alice, task_id)

    def test_admin_can_delete_assigned_task(self) -> None:
        task_id = self.task_service.create_task(
            self.admin,
            "Assigned task",
            "Description",
            "medium",
            None,
            "",
            self.bob.id,
            [],
        )
        self.task_service.delete_task(self.admin, task_id)
        with self.assertRaises(ValueError):
            self.task_service.get_task(self.admin, task_id)

    def test_manager_can_reassign_and_complete(self) -> None:
        task_id = self.task_service.create_task(
            self.alice,
            "Finish report",
            "Description",
            "critical",
            None,
            "",
            None,
            [],
        )
        self.task_service.update_task(
            self.maria,
            task_id,
            "Finish report",
            "Description",
            "critical",
            "under_progress",
            None,
            "",
            self.bob.id,
            [],
        )
        self.task_service.change_status(self.maria, task_id, STATUS_COMPLETED)
        task = self.task_service.get_task(self.maria, task_id)
        self.assertEqual(task.assigned_user_id, self.bob.id)
        self.assertEqual(task.status, STATUS_COMPLETED)

    def test_json_export_import_round_trip(self) -> None:
        sample_file = Path(self.temp_dir.name) / "note.txt"
        sample_file.write_text("hello")
        self.task_service.create_task(
            self.admin,
            "Backup test",
            "Description",
            "low",
            None,
            "",
            None,
            [str(sample_file)],
        )
        export_path = self.import_export.export_json_bundle(self.admin)
        fresh_db = Database(Path(self.temp_dir.name) / "import.db", self.security)
        fresh_db.initialize()
        fresh_users = UserService(fresh_db)
        fresh_task_service = TaskService(fresh_db, Path(self.temp_dir.name) / "import_attachments")
        fresh_task_service.attachments_dir.mkdir(parents=True, exist_ok=True)
        fresh_export = ImportExportService(fresh_db, fresh_task_service, fresh_users, Path(self.temp_dir.name) / "import_exports")
        fresh_export.exports_dir.mkdir(parents=True, exist_ok=True)
        admin = AuthService(fresh_db).login("admin", "admin123")
        result = fresh_export.import_json_bundle(admin, export_path)
        self.assertEqual(result["imported"], 1)

    def test_csv_export_creates_file(self) -> None:
        self.task_service.create_task(
            self.alice,
            "CSV Task",
            "Description",
            "medium",
            None,
            "",
            None,
            [],
        )
        export_path = self.import_export.export_csv(self.maria)
        self.assertTrue(Path(export_path).exists())

    def test_user_can_update_profile_and_password(self) -> None:
        updated = self.users.update_profile(self.alice.id, "alice2", "Alice Smith", "pw1", "newpass")
        self.assertEqual(updated.username, "alice2")
        self.assertEqual(updated.display_name, "Alice Smith")
        self.assertIsNotNone(self.auth.login("alice2", "newpass"))

    def test_custom_role_is_persisted_with_permissions(self) -> None:
        role = self.users.create_role(
            "Ops Lead",
            "Can manage users and roles.",
            [PERMISSION_MANAGE_USERS, PERMISSION_MANAGE_ROLES],
        )
        self.users.create_user("ops", "Ops", "pw4", role.id)
        ops = self.auth.login("ops", "pw4")
        self.assertIsNotNone(ops)
        assert ops is not None
        self.assertEqual(ops.role, "Ops Lead")
        self.assertTrue(ops.has_permission(PERMISSION_MANAGE_USERS))

    def test_passwords_are_stored_with_pbkdf2(self) -> None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE username = ?", ("alice",)).fetchone()
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$"))

    def test_task_text_is_encrypted_at_rest(self) -> None:
        task_id = self.task_service.create_task(
            self.alice,
            "Secret title",
            "Private body",
            "high",
            "2026-04-06T12:00:00",
            "hidden notes",
            None,
            [],
        )
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT title, description, deadline, more_info FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        self.assertNotIn("Secret title", row["title"])
        self.assertNotIn("Private body", row["description"])
        self.assertTrue(row["title"].startswith("task:"))


if __name__ == "__main__":
    unittest.main()
