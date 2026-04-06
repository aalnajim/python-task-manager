from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from task_app.config import LoginStateStore, get_app_paths
from task_app.data.database import Database
from task_app.services.auth import AuthService
from task_app.services.import_export import ImportExportService
from task_app.services.tasks import TaskService
from task_app.services.users import UserService
from task_app.ui.main_window import ForcePasswordChangeDialog, LoginDialog, MainWindow
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
    login_state = LoginStateStore(paths.login_state_path)
    return auth_service, user_service, task_service, import_export_service, login_state


class AppController:
    def __init__(self, app: QApplication):
        self.app = app
        (
            self.auth_service,
            self.user_service,
            self.task_service,
            self.import_export_service,
            self.login_state,
        ) = build_services()
        self.window: MainWindow | None = None

    def start(self) -> int:
        self.show_login()
        return self.app.exec()

    def show_login(self) -> None:
        state = self.login_state.load()
        login = LoginDialog(
            self.auth_service,
            remembered_username=str(state.get("username", "")),
            remember_me=bool(state.get("remember_me")),
        )
        if login.exec() != LoginDialog.DialogCode.Accepted or not login.user:
            self.app.quit()
            return
        self.login_state.save(login.remember_me.isChecked(), login.username.text())
        user = login.user
        if user.must_change_password:
            user = self.force_password_change(user)
            if user is None:
                self.show_login()
                return
        self.show_main_window(user)

    def force_password_change(self, user):
        while True:
            dialog = ForcePasswordChangeDialog(user.username)
            if dialog.exec() != ForcePasswordChangeDialog.DialogCode.Accepted:
                return None
            try:
                return self.user_service.update_profile(
                    user.id,
                    user.username,
                    user.display_name,
                    dialog.current_password.text(),
                    dialog.new_password.text(),
                )
            except Exception as exc:
                QMessageBox.warning(None, "Password not changed", str(exc))

    def show_main_window(self, user) -> None:
        self.window = MainWindow(user, self.task_service, self.user_service, self.import_export_service)
        self.window.logout_requested.connect(self.handle_logout)
        self.window.destroyed.connect(self._handle_window_closed)
        self.window.show()

    def handle_logout(self) -> None:
        if self.window is not None:
            self.window.logout_requested.disconnect(self.handle_logout)
            self.window.destroyed.disconnect(self._handle_window_closed)
            self.window.close()
            self.window = None
        self.show_login()

    def _handle_window_closed(self) -> None:
        if self.window is not None:
            self.window = None
            self.app.quit()


def main() -> int:
    app = QApplication(sys.argv)
    controller = AppController(app)
    return controller.start()
