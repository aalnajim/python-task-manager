from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from task_app.config import get_app_paths
from task_app.data.database import Database
from task_app.services.auth import AuthService
from task_app.services.import_export import ImportExportService
from task_app.services.tasks import TaskService
from task_app.services.users import UserService
from task_app.ui.main_window import LoginDialog, MainWindow
from task_app.utils.security import SecurityManager


def build_services():
    paths = get_app_paths()
    security = SecurityManager(paths.key_path)
    db = Database(paths.db_path, security)
    db.initialize()
    auth_service = AuthService(db)
    user_service = UserService(db)
    task_service = TaskService(db, paths.attachments_dir)
    import_export_service = ImportExportService(db, task_service, user_service, paths.exports_dir)
    return auth_service, user_service, task_service, import_export_service


def main() -> int:
    app = QApplication(sys.argv)
    auth_service, user_service, task_service, import_export_service = build_services()
    login = LoginDialog(auth_service)
    if login.exec() != LoginDialog.DialogCode.Accepted or not login.user:
        return 0
    window = MainWindow(login.user, task_service, user_service, import_export_service)
    window.show()
    return app.exec()
