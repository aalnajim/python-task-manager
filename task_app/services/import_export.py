from __future__ import annotations

import csv
import json
import shutil
import zipfile
from dataclasses import asdict
from pathlib import Path

from task_app.data.database import Database, utc_now
from task_app.models import Attachment, PERMISSION_EXPORT_DATA, PERMISSION_IMPORT_DATA, PERMISSION_VIEW_ALL_TASKS, Task, User
from task_app.services.tasks import TaskService
from task_app.services.users import UserService


class ImportExportService:
    def __init__(self, db: Database, task_service: TaskService, user_service: UserService, exports_dir: Path):
        self.db = db
        self.task_service = task_service
        self.user_service = user_service
        self.exports_dir = exports_dir

    def export_json_bundle(self, current_user: User, destination_zip: str | None = None) -> str:
        if not current_user.has_permission(PERMISSION_EXPORT_DATA):
            raise PermissionError("You do not have permission to export data.")
        tasks = self.task_service.list_tasks(current_user, include_all=current_user.has_permission(PERMISSION_VIEW_ALL_TASKS))
        users = self.user_service.list_users()
        timestamp = utc_now().replace(":", "-")
        bundle_dir = self.exports_dir / f"bundle_{timestamp}"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": utc_now(),
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "role": user.role,
                    "active": user.active,
                    "created_at": user.created_at,
                }
                for user in users
            ],
            "tasks": [],
        }
        attachments_dir = bundle_dir / "attachments"
        attachments_dir.mkdir(exist_ok=True)
        for task in tasks:
            attachments = self.task_service.list_attachments(task.id)
            histories = self.task_service.list_history(current_user, task.id)
            attachment_records = []
            for attachment in attachments:
                source = Path(attachment.stored_path)
                if source.exists():
                    dest_name = f"{attachment.id}_{attachment.original_name}"
                    shutil.copy2(source, attachments_dir / dest_name)
                    attachment_records.append(self._attachment_to_dict(attachment, dest_name))
            payload["tasks"].append(
                {
                    "task": asdict(task),
                    "attachments": attachment_records,
                    "history": [asdict(entry) for entry in histories],
                }
            )
        data_file = bundle_dir / "tasks.json"
        data_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        zip_path = Path(destination_zip) if destination_zip else self.exports_dir / f"task_export_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(data_file, arcname="tasks.json")
            for file_path in attachments_dir.glob("*"):
                archive.write(file_path, arcname=f"attachments/{file_path.name}")
        shutil.rmtree(bundle_dir, ignore_errors=True)
        return str(zip_path)

    def export_csv(self, current_user: User, destination_csv: str | None = None) -> str:
        if not current_user.has_permission(PERMISSION_EXPORT_DATA):
            raise PermissionError("You do not have permission to export data.")
        tasks = self.task_service.list_tasks(current_user, include_all=current_user.has_permission(PERMISSION_VIEW_ALL_TASKS))
        timestamp = utc_now().replace(":", "-")
        csv_path = Path(destination_csv) if destination_csv else self.exports_dir / f"task_export_{timestamp}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "id",
                    "title",
                    "description",
                    "priority",
                    "status",
                    "deadline",
                    "creator",
                    "assignee",
                    "more_info",
                    "attachment_count",
                    "attachment_names",
                    "created_at",
                    "updated_at",
                ],
            )
            writer.writeheader()
            for task in tasks:
                attachments = self.task_service.list_attachments(task.id)
                writer.writerow(
                    {
                        "id": task.id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority,
                        "status": task.status,
                        "deadline": task.deadline or "",
                        "creator": task.creator_name,
                        "assignee": task.assigned_name or "",
                        "more_info": task.more_info,
                        "attachment_count": len(attachments),
                        "attachment_names": ", ".join(item.original_name for item in attachments),
                        "created_at": task.created_at,
                        "updated_at": task.updated_at,
                    }
                )
        return str(csv_path)

    def import_json_bundle(self, current_user: User, zip_path: str, merge: bool = True) -> dict[str, int]:
        if not current_user.has_permission(PERMISSION_IMPORT_DATA):
            raise PermissionError("You do not have permission to import data.")
        temp_dir = self.exports_dir / f"import_{utc_now().replace(':', '-')}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(temp_dir)
        data = json.loads((temp_dir / "tasks.json").read_text(encoding="utf-8"))
        users_by_username = {user.username: user for user in self.user_service.list_users()}
        imported = 0
        skipped = 0
        existing_tasks = self.task_service.list_tasks(current_user, include_all=current_user.has_permission(PERMISSION_VIEW_ALL_TASKS))
        for task_payload in data.get("tasks", []):
            task_data = task_payload["task"]
            duplicate = next(
                (
                    task
                    for task in existing_tasks
                    if task.title == task_data["title"] and task.created_at == task_data["created_at"]
                ),
                None,
            )
            if duplicate and not merge:
                skipped += 1
                continue
            creator = users_by_username.get(self._find_username(data.get("users", []), task_data["creator_user_id"]))
            assigned = users_by_username.get(self._find_username(data.get("users", []), task_data["assigned_user_id"]))
            self.task_service.import_task_bundle(
                current_user=current_user,
                task_data=task_data,
                creator_user_id=creator.id if creator else current_user.id,
                assigned_user_id=assigned.id if assigned else None,
                attachments=task_payload.get("attachments", []),
                history=task_payload.get("history", []),
                attachment_root=temp_dir / "attachments",
            )
            imported += 1
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"imported": imported, "skipped": skipped}

    def preview_import(self, zip_path: str) -> dict[str, int]:
        with zipfile.ZipFile(zip_path, "r") as archive:
            with archive.open("tasks.json") as handle:
                data = json.loads(handle.read().decode("utf-8"))
        return {
            "tasks": len(data.get("tasks", [])),
            "users": len(data.get("users", [])),
        }

    def _find_username(self, users: list[dict], user_id: int | None) -> str | None:
        for user in users:
            if user["id"] == user_id:
                return user["username"]
        return None

    def _attachment_to_dict(self, attachment: Attachment, archive_name: str) -> dict[str, object]:
        return {
            "id": attachment.id,
            "original_name": attachment.original_name,
            "mime_type": attachment.mime_type,
            "file_size": attachment.file_size,
            "created_at": attachment.created_at,
            "archive_name": archive_name,
        }
