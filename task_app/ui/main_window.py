from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QHeaderView,
    QListView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from task_app.models import (
    ALL_PERMISSIONS,
    PERMISSION_ASSIGN_TASKS,
    PERMISSION_CREATE_TASKS,
    PERMISSION_DELETE_ALL_TASKS,
    PERMISSION_DELETE_OWN_TASKS,
    PERMISSION_EDIT_ALL_TASKS,
    PERMISSION_EDIT_OWN_TASKS,
    PERMISSION_EXPORT_DATA,
    PERMISSION_IMPORT_DATA,
    PERMISSION_LABELS,
    PERMISSION_MANAGE_ROLES,
    PERMISSION_MANAGE_USERS,
    PERMISSION_UPDATE_ALL_TASK_STATUS,
    PERMISSION_UPDATE_OWN_TASK_STATUS,
    PERMISSION_VIEW_ALL_TASKS,
    PRIORITIES,
    STATUS_NEW,
    TASK_STATUSES,
    Role,
    Task,
    User,
)
from task_app.services.auth import AuthService
from task_app.services.import_export import ImportExportService
from task_app.services.tasks import PermissionError, TaskService
from task_app.services.users import UserService


def priority_colors(priority: str) -> tuple[str, str]:
    mapping = {
        "low": ("#eaf3ee", "#2f5d50"),
        "medium": ("#fbf1d7", "#8a6a17"),
        "high": ("#f9dfdb", "#9c3d34"),
        "critical": ("#7a2630", "#ffffff"),
    }
    return mapping.get(priority, ("#f5f5f5", "#222222"))


def status_colors(task: Task) -> tuple[str, str]:
    mapping = {
        "new": ("#e8eef7", "#355070"),
        "under_progress": ("#eef2d7", "#6b7a1d"),
        "completed": ("#e3f0e7", "#32674a"),
    }
    return mapping.get(task.status, ("#eeeeee", "#222222"))


def deadline_colors(task: Task) -> tuple[str, str]:
    if not task.deadline_dt:
        return "", ""
    if task.is_overdue:
        return "#f9dfdb", "#9c3d34"
    deadline = task.deadline_dt
    if deadline and deadline.date() == datetime.now().date():
        return "#fbf1d7", "#8a6a17"
    return "#eaf3ee", "#2f5d50"


def overdue_colors(task: Task) -> tuple[str, str]:
    if task.is_overdue:
        return "#f9dfdb", "#9c3d34"
    return "#eef2f7", "#607080"


ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")


def apply_text_direction(widget, text: str) -> None:
    if ARABIC_RE.search(text or ""):
        widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        if hasattr(widget, "setAlignment"):
            widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    else:
        widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        if hasattr(widget, "setAlignment"):
            widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)


def apply_editor_text_direction(widget, text: str) -> None:
    option = widget.document().defaultTextOption()
    if ARABIC_RE.search(text or ""):
        widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        option.setAlignment(Qt.AlignmentFlag.AlignRight)
    else:
        widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        option.setTextDirection(Qt.LayoutDirection.LeftToRight)
        option.setAlignment(Qt.AlignmentFlag.AlignLeft)
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    widget.document().setDefaultTextOption(option)


def configure_combo_box(combo: QComboBox) -> None:
    view = QListView()
    view.setStyleSheet(
        """
        QListView {
            background: #ffffff;
            color: #243447;
            border: 1px solid #cfd8e6;
            outline: 0;
        }
        QListView::item {
            min-height: 28px;
            padding: 6px 10px;
            background: #ffffff;
            color: #243447;
        }
        QListView::item:hover {
            background: #dce8ff;
            color: #14223a;
        }
        QListView::item:selected {
            background: #2f6fed;
            color: #ffffff;
        }
        """
    )
    combo.setView(view)


def normalize_multiline(text: str) -> str:
    return text.replace("\u2029", "\n").replace("\u2028", "\n").replace("\r\n", "\n").replace("\r", "\n")


class LoginDialog(QDialog):
    def __init__(self, auth_service: AuthService, remembered_username: str = "", remember_me: bool = False):
        super().__init__()
        self.auth_service = auth_service
        self.user: User | None = None
        self.setWindowTitle("Task App Login")
        layout = QFormLayout(self)
        self.username = QLineEdit(remembered_username)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.remember_me = QCheckBox("Remember me")
        self.remember_me.setChecked(remember_me)
        layout.addRow("Username", self.username)
        layout.addRow("Password", self.password)
        layout.addRow("", self.remember_me)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.handle_login)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        if remembered_username:
            self.password.setFocus()
        else:
            self.username.setFocus()

    def handle_login(self) -> None:
        user = self.auth_service.login(self.username.text(), self.password.text())
        if not user:
            QMessageBox.warning(self, "Login failed", "Invalid username, password, or inactive account.")
            return
        self.user = user
        self.accept()


class UserDialog(QDialog):
    def __init__(self, roles: list[Role]):
        super().__init__()
        self.setWindowTitle("Create User")
        layout = QFormLayout(self)
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.role = QComboBox()
        for role in roles:
            self.role.addItem(role.name, role.id)
        configure_combo_box(self.role)
        layout.addRow("Username", self.username)
        layout.addRow("Display name", self.display_name)
        layout.addRow("Password", self.password)
        layout.addRow("Role", self.role)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class RoleDialog(QDialog):
    def __init__(self, role: Role | None = None):
        super().__init__()
        self.setWindowTitle("Edit Role" if role else "Create Role")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(role.name if role else "")
        self.description = QPlainTextEdit(role.description if role else "")
        self.description.setMaximumHeight(80)
        form.addRow("Role name", self.name)
        form.addRow("Description", self.description)
        layout.addLayout(form)

        permission_box = QGroupBox("Permissions")
        permission_layout = QVBoxLayout(permission_box)
        self.permission_checks: dict[str, QCheckBox] = {}
        selected = set(role.permissions if role else [])
        for permission in ALL_PERMISSIONS:
            checkbox = QCheckBox(PERMISSION_LABELS[permission])
            checkbox.setChecked(permission in selected)
            self.permission_checks[permission] = checkbox
            permission_layout.addWidget(checkbox)
        layout.addWidget(permission_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, list[str]]:
        return (
            self.name.text(),
            normalize_multiline(self.description.toPlainText()),
            [permission for permission, checkbox in self.permission_checks.items() if checkbox.isChecked()],
        )


class AccountSettingsDialog(QDialog):
    def __init__(self, current_user: User):
        super().__init__()
        self.setWindowTitle("Account Settings")
        layout = QFormLayout(self)
        self.username = QLineEdit(current_user.username)
        self.display_name = QLineEdit(current_user.display_name)
        self.current_password = QLineEdit()
        self.current_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Username", self.username)
        layout.addRow("Display name", self.display_name)
        layout.addRow("Current password", self.current_password)
        layout.addRow("New password", self.new_password)
        layout.addRow("Confirm new password", self.confirm_password)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def validate_and_accept(self) -> None:
        if self.new_password.text() != self.confirm_password.text():
            QMessageBox.warning(self, "Password mismatch", "The new password and confirmation do not match.")
            return
        self.accept()


class ForcePasswordChangeDialog(QDialog):
    def __init__(self, username: str):
        super().__init__()
        self.setWindowTitle("Change Password")
        layout = QFormLayout(self)
        notice = QLabel(f"The password for {username} must be changed before continuing.")
        notice.setWordWrap(True)
        self.current_password = QLineEdit()
        self.current_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow(notice)
        layout.addRow("Current password", self.current_password)
        layout.addRow("New password", self.new_password)
        layout.addRow("Confirm new password", self.confirm_password)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def validate_and_accept(self) -> None:
        if not self.new_password.text():
            QMessageBox.warning(self, "Password required", "Enter a new password.")
            return
        if self.new_password.text() == self.current_password.text():
            QMessageBox.warning(self, "Choose a new password", "The new password must be different from the current password.")
            return
        if self.new_password.text() != self.confirm_password.text():
            QMessageBox.warning(self, "Password mismatch", "The new password and confirmation do not match.")
            return
        self.accept()


class AssignTaskDialog(QDialog):
    def __init__(self, user_service: UserService, task: Task):
        super().__init__()
        self.setWindowTitle("Assign Task")
        layout = QFormLayout(self)
        self.assignee_input = QComboBox()
        self.assignee_input.addItem("Unassigned", None)
        for user in user_service.list_users():
            if user.active:
                self.assignee_input.addItem(f"{user.display_name} ({user.username})", user.id)
        configure_combo_box(self.assignee_input)
        if task.assigned_user_id:
            index = self.assignee_input.findData(task.assigned_user_id)
            if index >= 0:
                self.assignee_input.setCurrentIndex(index)
        layout.addRow("Task", QLabel(task.title))
        layout.addRow("Assignee", self.assignee_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class TaskDialog(QDialog):
    def __init__(self, user_service: UserService, current_user: User, task: Task | None = None):
        super().__init__()
        self.current_user = current_user
        self.task = task
        self.attachment_paths: list[str] = []
        self.setWindowTitle("Task Details" if task else "Create Task")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_input = QLineEdit(task.title if task else "")
        self.description_input = QPlainTextEdit(task.description if task else "")
        self.priority_input = QComboBox()
        self.priority_input.addItems(PRIORITIES)
        if task:
            self.priority_input.setCurrentText(task.priority)
        self.status_input = QComboBox()
        self.status_input.addItems(TASK_STATUSES)
        self.status_input.setCurrentText(task.status if task else STATUS_NEW)
        self.deadline_input = QDateTimeEdit()
        self.deadline_input.setCalendarPopup(True)
        self.deadline_input.setDateTime(datetime.now())
        self.no_deadline_checkbox = QCheckBox("No deadline")
        if task and task.deadline_dt:
            self.deadline_input.setDateTime(task.deadline_dt)
        else:
            self.no_deadline_checkbox.setChecked(True)
        self.more_info_input = QPlainTextEdit(task.more_info if task else "")
        apply_editor_text_direction(self.description_input, task.description if task else "")
        apply_editor_text_direction(self.more_info_input, task.more_info if task else "")
        self.assignee_input = QComboBox()
        self.assignee_input.addItem("Unassigned", None)
        for user in user_service.list_users():
            if user.active:
                self.assignee_input.addItem(f"{user.display_name} ({user.username})", user.id)
        configure_combo_box(self.assignee_input)
        if task and task.assigned_user_id:
            index = self.assignee_input.findData(task.assigned_user_id)
            if index >= 0:
                self.assignee_input.setCurrentIndex(index)
        if not current_user.has_permission(PERMISSION_ASSIGN_TASKS):
            self.assignee_input.setEnabled(False)
        if not task:
            self.status_input.setEnabled(False)
            self.status_input.setToolTip("New tasks always start with status 'new'.")
        form.addRow("Title", self.title_input)
        form.addRow("Description", self.description_input)
        form.addRow("Priority", self.priority_input)
        form.addRow("Status", self.status_input)
        form.addRow("Deadline", self.deadline_input)
        form.addRow("", self.no_deadline_checkbox)
        form.addRow("More info", self.more_info_input)
        form.addRow("Assignee", self.assignee_input)
        layout.addLayout(form)

        attachment_box = QGroupBox("New attachments")
        attachment_layout = QVBoxLayout(attachment_box)
        self.attachment_list = QListWidget()
        add_attachment = QPushButton("Add Attachment")
        add_attachment.clicked.connect(self.pick_attachments)
        attachment_layout.addWidget(self.attachment_list)
        attachment_layout.addWidget(add_attachment)
        layout.addWidget(attachment_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.description_input.textChanged.connect(
            lambda: apply_editor_text_direction(self.description_input, self.description_input.toPlainText())
        )
        self.more_info_input.textChanged.connect(
            lambda: apply_editor_text_direction(self.more_info_input, self.more_info_input.toPlainText())
        )

    def pick_attachments(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Attachments")
        for path in files:
            if path not in self.attachment_paths:
                self.attachment_paths.append(path)
                self.attachment_list.addItem(path)

    def values(self) -> dict[str, object]:
        deadline = None
        if not self.no_deadline_checkbox.isChecked():
            deadline = self.deadline_input.dateTime().toPython().replace(microsecond=0).isoformat()
        return {
            "title": self.title_input.text(),
            "description": normalize_multiline(self.description_input.toPlainText()),
            "priority": self.priority_input.currentText(),
            "status": self.status_input.currentText(),
            "deadline": deadline,
            "more_info": normalize_multiline(self.more_info_input.toPlainText()),
            "assigned_user_id": self.assignee_input.currentData(),
            "attachment_paths": list(self.attachment_paths),
        }


class TaskDetailsDialog(QDialog):
    def __init__(self, task_service: TaskService, current_user: User, task: Task, parent: QWidget | None = None):
        super().__init__(parent)
        self.task_service = task_service
        self.current_user = current_user
        self.task = task
        self.setWindowTitle(f"Task Details - {task.title}")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        summary_box = QGroupBox("Task Summary")
        summary_layout = QFormLayout(summary_box)
        title_label = QLabel(task.title)
        apply_text_direction(title_label, task.title)
        summary_layout.addRow("Title", title_label)
        summary_layout.addRow("Description", self._read_only_text(task.description or "-"))
        priority_bg, priority_fg = priority_colors(task.priority)
        status_bg, status_fg = status_colors(task)
        deadline_bg, deadline_fg = deadline_colors(task)
        summary_layout.addRow("Priority", self._pill_label(task.priority, priority_bg, priority_fg))
        summary_layout.addRow("Status", self._pill_label(task.status, status_bg, status_fg))
        if task.deadline:
            summary_layout.addRow(
                "Deadline",
                self._pill_label(task.deadline, deadline_bg or "#eef2f7", deadline_fg or "#607080"),
            )
        else:
            summary_layout.addRow("Deadline", QLabel("No deadline"))
        summary_layout.addRow("Owner", QLabel(task.creator_name))
        summary_layout.addRow("Assignee", QLabel(task.assigned_name or "Unassigned"))
        summary_layout.addRow("More info", self._read_only_text(task.more_info or "-"))
        summary_layout.addRow("Created", QLabel(task.created_at))
        summary_layout.addRow("Updated", QLabel(task.updated_at))
        layout.addWidget(summary_box)

        attachments = task_service.list_attachments(task.id)
        attachment_box = QGroupBox("Attachments")
        attachment_layout = QVBoxLayout(attachment_box)
        self.attachment_list = QListWidget()
        if attachments:
            for attachment in attachments:
                item = QListWidgetItem(f"{attachment.original_name} ({attachment.file_size} bytes)")
                item.setData(Qt.ItemDataRole.UserRole, (attachment.id, attachment.stored_path))
                self.attachment_list.addItem(item)
            self.attachment_list.itemDoubleClicked.connect(
                lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)[1]))
            )
        else:
            self.attachment_list.addItem("No attachments")
        attachment_layout.addWidget(self.attachment_list)
        remove_attachment_button = QPushButton("Remove Selected Attachment")
        remove_attachment_button.clicked.connect(self.remove_selected_attachment)
        attachment_layout.addWidget(remove_attachment_button)
        layout.addWidget(attachment_box)

        history = task_service.list_history(current_user, task.id)
        history_box = QGroupBox("History")
        history_layout = QVBoxLayout(history_box)
        history_list = QTextEdit()
        history_list.setReadOnly(True)
        if history:
            lines = []
            for entry in history:
                lines.append(f"{entry.timestamp} - {entry.actor_name} - {entry.action}: {entry.details}")
            history_list.setPlainText("\n".join(lines))
        else:
            history_list.setPlainText("No history")
        history_layout.addWidget(history_list)
        layout.addWidget(history_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _read_only_text(self, text: str) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setReadOnly(True)
        widget.setPlainText(normalize_multiline(text))
        widget.setMinimumHeight(80)
        apply_editor_text_direction(widget, text)
        return widget

    def _pill_label(self, text: str, bg: str, fg: str) -> QLabel:
        widget = QLabel(text)
        widget.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 600;
            }}
            """
        )
        return widget

    def remove_selected_attachment(self) -> None:
        item = self.attachment_list.currentItem()
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        attachment_id, _path = data
        if (
            QMessageBox.question(self, "Remove attachment", "Remove the selected attachment from this task?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.task_service.remove_attachment(self.current_user, attachment_id)
        except Exception as exc:
            QMessageBox.warning(self, "Could not remove attachment", str(exc))
            return
        self.attachment_list.takeItem(self.attachment_list.row(item))


class AdminPanelDialog(QDialog):
    current_user_changed = Signal()

    def __init__(self, user_service: UserService, task_service: TaskService, current_user: User):
        super().__init__()
        self.user_service = user_service
        self.task_service = task_service
        self.current_user = current_user
        self.setWindowTitle("Admin Panel")
        self.resize(800, 500)
        layout = QGridLayout(self)

        user_box = QGroupBox("Users")
        user_layout = QVBoxLayout(user_box)
        self.user_table = QTableWidget(0, 5)
        self.user_table.setHorizontalHeaderLabels(["ID", "Username", "Name", "Role", "Status"])
        user_layout.addWidget(self.user_table)
        user_buttons = QHBoxLayout()
        add_user = QPushButton("Add User")
        change_role = QPushButton("Change Role")
        toggle_user = QPushButton("Toggle Active")
        add_user.clicked.connect(self.create_user)
        change_role.clicked.connect(self.change_selected_user_role)
        toggle_user.clicked.connect(self.toggle_selected_user)
        user_buttons.addWidget(add_user)
        user_buttons.addWidget(change_role)
        user_buttons.addWidget(toggle_user)
        user_layout.addLayout(user_buttons)

        role_box = QGroupBox("Roles")
        role_layout = QVBoxLayout(role_box)
        self.role_table = QTableWidget(0, 4)
        self.role_table.setHorizontalHeaderLabels(["ID", "Name", "Permissions", "Type"])
        role_layout.addWidget(self.role_table)
        role_buttons = QHBoxLayout()
        add_role = QPushButton("Add Role")
        edit_role = QPushButton("Edit Role")
        add_role.clicked.connect(self.create_role)
        edit_role.clicked.connect(self.edit_selected_role)
        role_buttons.addWidget(add_role)
        role_buttons.addWidget(edit_role)
        role_layout.addLayout(role_buttons)

        task_box = QGroupBox("Visible Tasks")
        task_layout = QVBoxLayout(task_box)
        self.task_table = QTableWidget(0, 5)
        self.task_table.setHorizontalHeaderLabels(["ID", "Title", "Priority", "Status", "Assignee"])
        task_layout.addWidget(self.task_table)

        layout.addWidget(user_box, 0, 0)
        layout.addWidget(role_box, 0, 1)
        layout.addWidget(task_box, 1, 0, 1, 2)
        self.refresh()

    def refresh(self) -> None:
        roles = self.user_service.list_roles()
        self.role_table.setRowCount(len(roles))
        for row, role in enumerate(roles):
            self.role_table.setItem(row, 0, QTableWidgetItem(str(role.id)))
            self.role_table.setItem(row, 1, QTableWidgetItem(role.name))
            self.role_table.setItem(row, 2, QTableWidgetItem(", ".join(PERMISSION_LABELS.get(item, item) for item in role.permissions)))
            self.role_table.setItem(row, 3, QTableWidgetItem("System" if role.is_system else "Custom"))

        users = self.user_service.list_users()
        self.user_table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.user_table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self.user_table.setItem(row, 1, QTableWidgetItem(user.username))
            self.user_table.setItem(row, 2, QTableWidgetItem(user.display_name))
            self.user_table.setItem(row, 3, QTableWidgetItem(user.role))
            self.user_table.setItem(row, 4, QTableWidgetItem("active" if user.active else "inactive"))
        tasks = self.task_service.list_tasks(self.current_user, include_all=self.current_user.has_permission(PERMISSION_VIEW_ALL_TASKS))
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.task_table.setItem(row, 0, QTableWidgetItem(str(task.id)))
            self.task_table.setItem(row, 1, QTableWidgetItem(task.title))
            self.task_table.setItem(row, 2, QTableWidgetItem(task.priority))
            self.task_table.setItem(row, 3, QTableWidgetItem(task.status))
            self.task_table.setItem(row, 4, QTableWidgetItem(task.assigned_name or "Unassigned"))

    def create_user(self) -> None:
        if not self.current_user.has_permission(PERMISSION_MANAGE_USERS):
            QMessageBox.warning(self, "Restricted", "You do not have permission to create users.")
            return
        roles = self.user_service.list_roles()
        dialog = UserDialog(roles)
        if dialog.exec():
            try:
                self.user_service.create_user(
                    dialog.username.text(),
                    dialog.display_name.text(),
                    dialog.password.text(),
                    int(dialog.role.currentData()),
                )
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Could not create user", str(exc))

    def create_role(self) -> None:
        if not self.current_user.has_permission(PERMISSION_MANAGE_ROLES):
            QMessageBox.warning(self, "Restricted", "You do not have permission to create roles.")
            return
        dialog = RoleDialog()
        if not dialog.exec():
            return
        try:
            self.user_service.create_role(*dialog.values())
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not create role", str(exc))

    def edit_selected_role(self) -> None:
        if not self.current_user.has_permission(PERMISSION_MANAGE_ROLES):
            QMessageBox.warning(self, "Restricted", "You do not have permission to edit roles.")
            return
        row = self.role_table.currentRow()
        if row < 0:
            return
        role_id = int(self.role_table.item(row, 0).text())
        role = self.user_service.get_role(role_id)
        dialog = RoleDialog(role)
        if not dialog.exec():
            return
        try:
            self.user_service.update_role(role_id, *dialog.values())
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not update role", str(exc))

    def change_selected_user_role(self) -> None:
        if not self.current_user.has_permission(PERMISSION_MANAGE_USERS):
            QMessageBox.warning(self, "Restricted", "You do not have permission to change user roles.")
            return
        row = self.user_table.currentRow()
        if row < 0:
            return
        user_id = int(self.user_table.item(row, 0).text())
        roles = self.user_service.list_roles()
        dialog = QDialog(self)
        dialog.setWindowTitle("Change User Role")
        layout = QFormLayout(dialog)
        role_input = QComboBox()
        current_role = self.user_table.item(row, 3).text()
        for role in roles:
            role_input.addItem(role.name, role.id)
            if role.name == current_role:
                role_input.setCurrentIndex(role_input.count() - 1)
        configure_combo_box(role_input)
        layout.addRow("Role", role_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if not dialog.exec():
            return
        try:
            self.user_service.update_user_role(self.current_user.id, user_id, int(role_input.currentData()))
            if user_id == self.current_user.id:
                self.current_user = self.user_service.get_user(self.current_user.id)
                self.current_user_changed.emit()
                if not (
                    self.current_user.has_permission(PERMISSION_MANAGE_USERS)
                    or self.current_user.has_permission(PERMISSION_MANAGE_ROLES)
                ):
                    self.accept()
                    return
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not change role", str(exc))

    def toggle_selected_user(self) -> None:
        if not self.current_user.has_permission(PERMISSION_MANAGE_USERS):
            QMessageBox.warning(self, "Restricted", "You do not have permission to manage users.")
            return
        row = self.user_table.currentRow()
        if row < 0:
            return
        user_id = int(self.user_table.item(row, 0).text())
        active = self.user_table.item(row, 4).text() == "inactive"
        try:
            self.user_service.set_user_active(self.current_user.id, user_id, active)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not update user", str(exc))


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(
        self,
        current_user: User,
        task_service: TaskService,
        user_service: UserService,
        import_export_service: ImportExportService,
    ):
        super().__init__()
        self.current_user = current_user
        self.task_service = task_service
        self.user_service = user_service
        self.import_export_service = import_export_service
        self.setWindowTitle(f"Task App - {current_user.display_name}")
        self.resize(1100, 700)
        self.setStyleSheet(
            """
            QMainWindow, QDialog {
                background: #f5f7fb;
                color: #243447;
            }
            QGroupBox {
                border: 1px solid #d7dee9;
                border-radius: 12px;
                margin-top: 12px;
                font-weight: 600;
                background: #ffffff;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                color: #31445a;
            }
            QPushButton {
                background: #2f6fed;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #245fd0;
            }
            QLineEdit, QTextEdit, QComboBox, QDateTimeEdit, QListWidget, QTableWidget {
                background: white;
                border: 1px solid #d7dee9;
                border-radius: 8px;
                padding: 6px;
                color: #243447;
            }
            QComboBox QAbstractItemView {
                selection-background-color: #2f6fed;
                selection-color: #ffffff;
                background: #ffffff;
                color: #243447;
                alternate-background-color: #f7f9fc;
                outline: 0;
                border: 1px solid #cfd8e6;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 6px 10px;
                background: #ffffff;
                color: #243447;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #dce8ff;
                color: #14223a;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #2f6fed;
                color: #ffffff;
            }
            QTableWidget {
                gridline-color: #e5e9f0;
                selection-background-color: #dce8ff;
                selection-color: #14223a;
            }
            QHeaderView::section {
                background: #eef3fb;
                color: #31445a;
                padding: 6px;
                border: 1px solid #d7dee9;
                font-weight: 600;
            }
            """
        )

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.main_layout = layout

        dashboard = QGroupBox("Dashboard")
        dashboard_layout = QGridLayout(dashboard)
        self.total_label = QLabel()
        self.overdue_label = QLabel()
        self.today_label = QLabel()
        self.completed_label = QLabel()
        dashboard_layout.addWidget(self.total_label, 0, 0)
        dashboard_layout.addWidget(self.overdue_label, 0, 1)
        dashboard_layout.addWidget(self.today_label, 1, 0)
        dashboard_layout.addWidget(self.completed_label, 1, 1)
        layout.addWidget(dashboard)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tasks...")
        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", "")
        for status in TASK_STATUSES:
            self.status_filter.addItem(status, status)
        self.priority_filter = QComboBox()
        self.priority_filter.addItem("All priorities", "")
        for priority in PRIORITIES:
            self.priority_filter.addItem(priority, priority)
        configure_combo_box(self.status_filter)
        configure_combo_box(self.priority_filter)
        refresh_button = QPushButton("Apply Filters")
        refresh_button.clicked.connect(self.refresh_tasks)
        filter_row.addWidget(self.search_input)
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(self.priority_filter)
        filter_row.addWidget(refresh_button)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Title", "Priority", "Status", "Deadline", "Owner", "Assignee", "Overdue"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self.view_task_details())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self._build_action_row()
        self._build_menus()
        self.refresh_tasks()

    def _build_menus(self) -> None:
        menu = self.menuBar()
        menu.clear()
        file_menu = menu.addMenu("File")
        export_json = QAction("Export JSON Bundle", self)
        export_json.triggered.connect(self.export_json)
        export_csv = QAction("Export CSV", self)
        export_csv.triggered.connect(self.export_csv)
        import_json = QAction("Import JSON Bundle", self)
        import_json.triggered.connect(self.import_json)
        if self.current_user.has_permission(PERMISSION_EXPORT_DATA):
            file_menu.addAction(export_json)
            file_menu.addAction(export_csv)
        if self.current_user.has_permission(PERMISSION_IMPORT_DATA):
            file_menu.addAction(import_json)
        account_menu = menu.addMenu("Account")
        account_settings = QAction("Profile & Password", self)
        account_settings.triggered.connect(self.open_account_settings)
        logout_action = QAction("Log Out", self)
        logout_action.triggered.connect(self.request_logout)
        account_menu.addAction(account_settings)
        account_menu.addSeparator()
        account_menu.addAction(logout_action)
        if self.current_user.has_permission(PERMISSION_MANAGE_USERS) or self.current_user.has_permission(PERMISSION_MANAGE_ROLES):
            admin_menu = menu.addMenu("Admin")
            admin_panel = QAction("Open Admin Panel", self)
            admin_panel.triggered.connect(self.open_admin_panel)
            admin_menu.addAction(admin_panel)

    def _build_action_row(self) -> None:
        if hasattr(self, "action_row_widget"):
            self.main_layout.removeWidget(self.action_row_widget)
            self.action_row_widget.deleteLater()
        self.action_row_widget = QWidget()
        action_row = QHBoxLayout(self.action_row_widget)
        action_row.setContentsMargins(0, 0, 0, 0)

        def add_button(label: str, handler, visible: bool = True) -> None:
            if not visible:
                return
            button = QPushButton(label)
            button.clicked.connect(handler)
            action_row.addWidget(button)

        add_button("New Task", self.create_task, self.current_user.has_permission(PERMISSION_CREATE_TASKS))
        add_button("View Details", self.view_task_details, True)
        add_button("Assign/Reassign", self.assign_task, self.current_user.has_permission(PERMISSION_ASSIGN_TASKS))
        add_button(
            "Edit Task",
            self.edit_task,
            self.current_user.has_permission(PERMISSION_EDIT_OWN_TASKS) or self.current_user.has_permission(PERMISSION_EDIT_ALL_TASKS),
        )
        add_button(
            "Delete Task",
            self.delete_task,
            self.current_user.has_permission(PERMISSION_DELETE_OWN_TASKS) or self.current_user.has_permission(PERMISSION_DELETE_ALL_TASKS),
        )
        can_update_status = self.current_user.has_permission(PERMISSION_UPDATE_OWN_TASK_STATUS) or self.current_user.has_permission(PERMISSION_UPDATE_ALL_TASK_STATUS)
        add_button("Mark In Progress", lambda: self.set_status("under_progress"), can_update_status)
        add_button("Mark Completed", lambda: self.set_status("completed"), can_update_status)
        add_button("View History", self.show_history, True)
        add_button("Export JSON", self.export_json, self.current_user.has_permission(PERMISSION_EXPORT_DATA))
        add_button("Export CSV", self.export_csv, self.current_user.has_permission(PERMISSION_EXPORT_DATA))
        add_button("Import JSON", self.import_json, self.current_user.has_permission(PERMISSION_IMPORT_DATA))
        self.main_layout.addWidget(self.action_row_widget)

    def sync_current_user(self) -> None:
        self.current_user = self.user_service.get_user(self.current_user.id)
        self.setWindowTitle(f"Task App - {self.current_user.display_name}")
        self._build_action_row()
        self._build_menus()
        self.refresh_tasks()

    def selected_task_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return int(self.table.item(row, 0).text())

    def refresh_tasks(self) -> None:
        tasks = self.task_service.list_tasks(
            self.current_user,
            query=self.search_input.text(),
            status=self.status_filter.currentData(),
            priority=self.priority_filter.currentData(),
            include_all=self.current_user.has_permission(PERMISSION_VIEW_ALL_TASKS),
        )
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            values = [
                str(task.id),
                task.title,
                task.priority,
                task.status,
                task.deadline or "",
                task.creator_name,
                task.assigned_name or "Unassigned",
                "Yes" if task.is_overdue else "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                self._apply_task_colors(item, task, col)
                self.table.setItem(row, col, item)
        stats = self.task_service.stats_for(self.current_user)
        self.total_label.setText(f"Total tasks: {stats['total']}")
        self.overdue_label.setText(f"Overdue: {stats['overdue']}")
        self.today_label.setText(f"Due today: {stats['due_today']}")
        self.completed_label.setText(f"Completed: {stats['completed']}")

    def _apply_task_colors(self, item: QTableWidgetItem, task: Task, col: int) -> None:
        if col == 2:
            bg, fg = priority_colors(task.priority)
            item.setBackground(QColor(bg))
            item.setForeground(QColor(fg))
            return
        if col == 3:
            bg, fg = status_colors(task)
            item.setBackground(QColor(bg))
            item.setForeground(QColor(fg))
            return
        if col == 4:
            bg, fg = deadline_colors(task)
            if bg and fg:
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
            return
        if col == 7:
            bg, fg = overdue_colors(task)
            item.setBackground(QColor(bg))
            item.setForeground(QColor(fg))
            return

    def view_task_details(self) -> None:
        task_id = self.selected_task_id()
        if task_id is None:
            return
        task = self.task_service.get_task(self.current_user, task_id)
        dialog = TaskDetailsDialog(self.task_service, self.current_user, task, self)
        dialog.exec()

    def create_task(self) -> None:
        if not self.current_user.has_permission(PERMISSION_CREATE_TASKS):
            QMessageBox.warning(self, "Restricted", "You do not have permission to create tasks.")
            return
        dialog = TaskDialog(self.user_service, self.current_user)
        if dialog.exec():
            try:
                values = dialog.values()
                self.task_service.create_task(
                    self.current_user,
                    title=values["title"],
                    description=values["description"],
                    priority=values["priority"],
                    deadline=values["deadline"],
                    more_info=values["more_info"],
                    assigned_user_id=values["assigned_user_id"],
                    attachment_paths=values["attachment_paths"],
                )
                self.refresh_tasks()
            except Exception as exc:
                QMessageBox.warning(self, "Task not created", str(exc))

    def assign_task(self) -> None:
        task_id = self.selected_task_id()
        if task_id is None:
            return
        if not self.current_user.has_permission(PERMISSION_ASSIGN_TASKS):
            QMessageBox.warning(self, "Restricted", "You do not have permission to assign tasks.")
            return
        task = self.task_service.get_task(self.current_user, task_id)
        dialog = AssignTaskDialog(self.user_service, task)
        if not dialog.exec():
            return
        try:
            self.task_service.update_task(
                self.current_user,
                task_id,
                title=task.title,
                description=task.description,
                priority=task.priority,
                status=task.status,
                deadline=task.deadline,
                more_info=task.more_info,
                assigned_user_id=dialog.assignee_input.currentData(),
                attachment_paths=[],
            )
            self.refresh_tasks()
        except Exception as exc:
            QMessageBox.warning(self, "Assignment failed", str(exc))

    def edit_task(self) -> None:
        if not (
            self.current_user.has_permission(PERMISSION_EDIT_OWN_TASKS)
            or self.current_user.has_permission(PERMISSION_EDIT_ALL_TASKS)
        ):
            QMessageBox.warning(self, "Restricted", "You do not have permission to edit tasks.")
            return
        task_id = self.selected_task_id()
        if task_id is None:
            return
        task = self.task_service.get_task(self.current_user, task_id)
        dialog = TaskDialog(self.user_service, self.current_user, task)
        if dialog.exec():
            try:
                self.task_service.update_task(self.current_user, task_id, **dialog.values())
                self.refresh_tasks()
            except Exception as exc:
                QMessageBox.warning(self, "Task not updated", str(exc))

    def delete_task(self) -> None:
        if not (
            self.current_user.has_permission(PERMISSION_DELETE_OWN_TASKS)
            or self.current_user.has_permission(PERMISSION_DELETE_ALL_TASKS)
        ):
            QMessageBox.warning(self, "Restricted", "You do not have permission to delete tasks.")
            return
        task_id = self.selected_task_id()
        if task_id is None:
            return
        if QMessageBox.question(self, "Delete task", "Are you sure you want to delete this task?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.task_service.delete_task(self.current_user, task_id)
            self.refresh_tasks()
        except PermissionError as exc:
            QMessageBox.warning(self, "Not allowed", str(exc))

    def set_status(self, status: str) -> None:
        if not (
            self.current_user.has_permission(PERMISSION_UPDATE_OWN_TASK_STATUS)
            or self.current_user.has_permission(PERMISSION_UPDATE_ALL_TASK_STATUS)
        ):
            QMessageBox.warning(self, "Restricted", "You do not have permission to update task status.")
            return
        task_id = self.selected_task_id()
        if task_id is None:
            return
        try:
            self.task_service.change_status(self.current_user, task_id, status)
            self.refresh_tasks()
        except Exception as exc:
            QMessageBox.warning(self, "Status not changed", str(exc))

    def show_history(self) -> None:
        task_id = self.selected_task_id()
        if task_id is None:
            return
        task = self.task_service.get_task(self.current_user, task_id)
        attachments = self.task_service.list_attachments(task_id)
        history = self.task_service.list_history(self.current_user, task_id)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Task History - {task.title}")
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        attachment_list = QListWidget()
        for attachment in attachments:
            item = QListWidgetItem(f"{attachment.original_name} ({attachment.file_size} bytes)")
            item.setData(Qt.ItemDataRole.UserRole, attachment.stored_path)
            attachment_list.addItem(item)
        attachment_list.itemDoubleClicked.connect(
            lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)))
        )
        history_list = QListWidget()
        for entry in history:
            history_list.addItem(f"{entry.timestamp} - {entry.actor_name} - {entry.action}: {entry.details}")
        layout.addWidget(QLabel("Attachments (double-click to open)"))
        layout.addWidget(attachment_list)
        layout.addWidget(QLabel("History"))
        layout.addWidget(history_list)
        dialog.exec()

    def export_json(self) -> None:
        if not self.current_user.has_permission(PERMISSION_EXPORT_DATA):
            QMessageBox.warning(self, "Restricted", "You do not have permission to export data.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Export JSON Bundle", str(Path.home() / "tasks_export.zip"), "Zip Files (*.zip)")
        if not file_path:
            return
        result = self.import_export_service.export_json_bundle(self.current_user, file_path)
        QMessageBox.information(self, "Export complete", f"JSON bundle exported to:\n{result}")

    def export_csv(self) -> None:
        if not self.current_user.has_permission(PERMISSION_EXPORT_DATA):
            QMessageBox.warning(self, "Restricted", "You do not have permission to export data.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(Path.home() / "tasks_export.csv"), "CSV Files (*.csv)")
        if not file_path:
            return
        result = self.import_export_service.export_csv(self.current_user, file_path)
        QMessageBox.information(self, "Export complete", f"CSV exported to:\n{result}")

    def import_json(self) -> None:
        if not self.current_user.has_permission(PERMISSION_IMPORT_DATA):
            QMessageBox.warning(self, "Restricted", "You do not have permission to import data.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Import JSON Bundle", "", "Zip Files (*.zip)")
        if not file_path:
            return
        preview = self.import_export_service.preview_import(file_path)
        confirm = QMessageBox.question(
            self,
            "Confirm import",
            f"Found {preview['tasks']} tasks and {preview['users']} users in the bundle.\nImport now?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self.import_export_service.import_json_bundle(self.current_user, file_path, merge=True)
        QMessageBox.information(
            self,
            "Import complete",
            f"Imported {result['imported']} tasks.\nSkipped {result['skipped']} tasks.",
        )
        self.refresh_tasks()

    def open_admin_panel(self) -> None:
        if not (
            self.current_user.has_permission(PERMISSION_MANAGE_USERS)
            or self.current_user.has_permission(PERMISSION_MANAGE_ROLES)
        ):
            QMessageBox.warning(self, "Restricted", "You do not have permission to access the admin panel.")
            return
        dialog = AdminPanelDialog(self.user_service, self.task_service, self.current_user)
        dialog.current_user_changed.connect(self.sync_current_user)
        dialog.exec()
        self.sync_current_user()

    def open_account_settings(self) -> None:
        dialog = AccountSettingsDialog(self.current_user)
        if not dialog.exec():
            return
        try:
            self.current_user = self.user_service.update_profile(
                self.current_user.id,
                dialog.username.text(),
                dialog.display_name.text(),
                dialog.current_password.text(),
                dialog.new_password.text(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Could not update account", str(exc))
            return
        self.setWindowTitle(f"Task App - {self.current_user.display_name}")
        QMessageBox.information(self, "Account updated", "Your account settings were saved.")

    def request_logout(self) -> None:
        if QMessageBox.question(self, "Log out", "Do you want to log out of the current session?") != QMessageBox.StandardButton.Yes:
            return
        self.logout_requested.emit()
