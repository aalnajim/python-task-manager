from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
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

from task_app.models import PRIORITIES, ROLE_ADMIN, STATUS_NEW, TASK_STATUSES, Task, User
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
    def __init__(self, auth_service: AuthService):
        super().__init__()
        self.auth_service = auth_service
        self.user: User | None = None
        self.setWindowTitle("Task App Login")
        layout = QFormLayout(self)
        self.username = QLineEdit("admin")
        self.password = QLineEdit("admin123")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Username", self.username)
        layout.addRow("Password", self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.handle_login)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def handle_login(self) -> None:
        user = self.auth_service.login(self.username.text(), self.password.text())
        if not user:
            QMessageBox.warning(self, "Login failed", "Invalid username, password, or inactive account.")
            return
        self.user = user
        self.accept()


class UserDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Create User")
        layout = QFormLayout(self)
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.role = QComboBox()
        self.role.addItems(["user", "admin"])
        configure_combo_box(self.role)
        layout.addRow("Username", self.username)
        layout.addRow("Display name", self.display_name)
        layout.addRow("Password", self.password)
        layout.addRow("Role", self.role)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


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
        if not current_user.is_admin:
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
        summary_layout.addRow("Priority", QLabel(task.priority))
        summary_layout.addRow("Status", QLabel(task.status))
        summary_layout.addRow("Deadline", QLabel(task.deadline or "No deadline"))
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
    def __init__(self, user_service: UserService, task_service: TaskService, current_user: User):
        super().__init__()
        self.user_service = user_service
        self.task_service = task_service
        self.current_user = current_user
        self.setWindowTitle("Admin Panel")
        self.resize(800, 500)
        layout = QHBoxLayout(self)

        user_box = QGroupBox("Users")
        user_layout = QVBoxLayout(user_box)
        self.user_table = QTableWidget(0, 4)
        self.user_table.setHorizontalHeaderLabels(["ID", "Username", "Name", "Role/Status"])
        user_layout.addWidget(self.user_table)
        buttons_row = QHBoxLayout()
        add_user = QPushButton("Add User")
        toggle_user = QPushButton("Toggle Active")
        add_user.clicked.connect(self.create_user)
        toggle_user.clicked.connect(self.toggle_selected_user)
        buttons_row.addWidget(add_user)
        buttons_row.addWidget(toggle_user)
        user_layout.addLayout(buttons_row)

        task_box = QGroupBox("All Tasks")
        task_layout = QVBoxLayout(task_box)
        self.task_table = QTableWidget(0, 5)
        self.task_table.setHorizontalHeaderLabels(["ID", "Title", "Priority", "Status", "Assignee"])
        task_layout.addWidget(self.task_table)

        layout.addWidget(user_box)
        layout.addWidget(task_box)
        self.refresh()

    def refresh(self) -> None:
        users = self.user_service.list_users()
        self.user_table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.user_table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self.user_table.setItem(row, 1, QTableWidgetItem(user.username))
            self.user_table.setItem(row, 2, QTableWidgetItem(user.display_name))
            self.user_table.setItem(row, 3, QTableWidgetItem(f"{user.role} / {'active' if user.active else 'inactive'}"))
        tasks = self.task_service.list_tasks(self.current_user, include_all=True)
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.task_table.setItem(row, 0, QTableWidgetItem(str(task.id)))
            self.task_table.setItem(row, 1, QTableWidgetItem(task.title))
            self.task_table.setItem(row, 2, QTableWidgetItem(task.priority))
            self.task_table.setItem(row, 3, QTableWidgetItem(task.status))
            self.task_table.setItem(row, 4, QTableWidgetItem(task.assigned_name or "Unassigned"))

    def create_user(self) -> None:
        dialog = UserDialog()
        if dialog.exec():
            try:
                self.user_service.create_user(
                    dialog.username.text(),
                    dialog.display_name.text(),
                    dialog.password.text(),
                    dialog.role.currentText(),
                )
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Could not create user", str(exc))

    def toggle_selected_user(self) -> None:
        row = self.user_table.currentRow()
        if row < 0:
            return
        user_id = int(self.user_table.item(row, 0).text())
        role_status = self.user_table.item(row, 3).text()
        active = "inactive" in role_status
        self.user_service.set_user_active(user_id, active)
        self.refresh()


class MainWindow(QMainWindow):
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

        action_row = QHBoxLayout()
        create_button = QPushButton("New Task")
        details_button = QPushButton("View Details")
        assign_button = QPushButton("Assign/Reassign")
        edit_button = QPushButton("Edit Task")
        delete_button = QPushButton("Delete Task")
        status_button = QPushButton("Mark In Progress")
        done_button = QPushButton("Mark Completed")
        history_button = QPushButton("View History")
        export_json_button = QPushButton("Export JSON")
        export_csv_button = QPushButton("Export CSV")
        import_button = QPushButton("Import JSON")
        action_row.addWidget(create_button)
        action_row.addWidget(details_button)
        action_row.addWidget(assign_button)
        action_row.addWidget(edit_button)
        action_row.addWidget(delete_button)
        action_row.addWidget(status_button)
        action_row.addWidget(done_button)
        action_row.addWidget(history_button)
        action_row.addWidget(export_json_button)
        action_row.addWidget(export_csv_button)
        action_row.addWidget(import_button)
        layout.addLayout(action_row)

        create_button.clicked.connect(self.create_task)
        details_button.clicked.connect(self.view_task_details)
        assign_button.clicked.connect(self.assign_task)
        edit_button.clicked.connect(self.edit_task)
        delete_button.clicked.connect(self.delete_task)
        status_button.clicked.connect(lambda: self.set_status("under_progress"))
        done_button.clicked.connect(lambda: self.set_status("completed"))
        history_button.clicked.connect(self.show_history)
        export_json_button.clicked.connect(self.export_json)
        export_csv_button.clicked.connect(self.export_csv)
        import_button.clicked.connect(self.import_json)

        self._build_menus()
        self.refresh_tasks()

    def _build_menus(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        export_json = QAction("Export JSON Bundle", self)
        export_json.triggered.connect(self.export_json)
        export_csv = QAction("Export CSV", self)
        export_csv.triggered.connect(self.export_csv)
        import_json = QAction("Import JSON Bundle", self)
        import_json.triggered.connect(self.import_json)
        file_menu.addAction(export_json)
        file_menu.addAction(export_csv)
        file_menu.addAction(import_json)
        account_menu = menu.addMenu("Account")
        account_settings = QAction("Profile & Password", self)
        account_settings.triggered.connect(self.open_account_settings)
        account_menu.addAction(account_settings)
        if self.current_user.role == ROLE_ADMIN:
            admin_menu = menu.addMenu("Admin")
            admin_panel = QAction("Open Admin Panel", self)
            admin_panel.triggered.connect(self.open_admin_panel)
            admin_menu.addAction(admin_panel)

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
            include_all=False,
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
        if not self.current_user.is_admin:
            QMessageBox.warning(self, "Restricted", "Only admin can assign or reassign tasks.")
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
        file_path, _ = QFileDialog.getSaveFileName(self, "Export JSON Bundle", str(Path.home() / "tasks_export.zip"), "Zip Files (*.zip)")
        if not file_path:
            return
        result = self.import_export_service.export_json_bundle(self.current_user, file_path)
        QMessageBox.information(self, "Export complete", f"JSON bundle exported to:\n{result}")

    def export_csv(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(Path.home() / "tasks_export.csv"), "CSV Files (*.csv)")
        if not file_path:
            return
        result = self.import_export_service.export_csv(self.current_user, file_path)
        QMessageBox.information(self, "Export complete", f"CSV exported to:\n{result}")

    def import_json(self) -> None:
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
        if not self.current_user.is_admin:
            QMessageBox.warning(self, "Restricted", "Only admin can access the admin panel.")
            return
        dialog = AdminPanelDialog(self.user_service, self.task_service, self.current_user)
        dialog.exec()
        self.refresh_tasks()

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
