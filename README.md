# Python Task Manager

Local-first desktop task manager built with Python, PySide6, and SQLite, designed for macOS and structured so it can later be packaged as a `.app`.

## Highlights

- Desktop UI built with `PySide6`
- Local multi-user task management
- Role-based permissions with admin-managed roles
- Task assignment and reassignment
- Task priorities, deadlines, notes, and attachments
- Status tracking: `new`, `under_progress`, `completed`
- JSON export/import and CSV export
- Attachment storage managed by the app
- Task history and audit trail
- Password-based protected task access and encrypted task data

## Features

### Task Management

- Create tasks with title, description, priority, deadline, more info, and attachments
- Edit tasks after creation
- Mark tasks as `new`, `under_progress`, or `completed`
- View detailed task information, attachment list, and history
- Assign or reassign tasks as admin
- Remove individual attachments from a task

### Roles and Permissions

- Admins can create custom roles with fixed permissions
- Users are assigned to one existing role
- A user is considered admin-capable when their role includes both `manage_users` and `manage_roles`
- Permissions can control access to:
  - user management
  - role management
  - viewing all tasks
  - creating tasks
  - editing own tasks
  - editing all tasks
  - deleting own tasks
  - deleting all tasks
  - assigning tasks
  - updating own task status
  - updating all task status
  - export/import tools
- The main UI hides actions the current user is not allowed to use
- If a user changes their own role and loses access, the UI refreshes immediately without requiring logout

### Import and Export

- Export task data to:
  - `JSON` bundle with attachment files
  - `CSV` for spreadsheet/reporting workflows
- Import tasks from a JSON bundle

### Security

- Passwords are stored using salted `PBKDF2-SHA256`
- Task content is encrypted at rest
- Task decryption follows per-user access rules
- The bootstrap admin account is forced to change its password before entering the app
- The login dialog supports `Remember me` for the username only
- The app includes an in-session `Log Out` action
- The built-in `Administrator` role is protected from accidental edits
- The original bootstrap admin account cannot be demoted or deactivated by anyone, including itself
- The app prevents changes that would leave zero active admin-capable users
- Task access is intended for:
  - the creator
  - the assignee
  - users with task-visibility permissions when access is granted

## Project Structure

```text
task_app/
  app.py
  config.py
  models.py
  data/
    database.py
  services/
    auth.py
    import_export.py
    tasks.py
    users.py
  ui/
    main_window.py
  utils/
    security.py
tests/
  test_services.py
```

## Requirements

- Python 3.14 or compatible recent Python 3
- macOS recommended

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python -m task_app
```

## Login Flow

The login screen now:

- starts with empty credentials by default
- supports a `Remember me` checkbox that stores only the username in `~/.task_app/login_state.json`
- forces the bootstrap admin to change password on first successful login
- supports logging out from inside the app via `Account -> Log Out`

## Default Local Admin

The initial local bootstrap admin account is:

- Username: `admin`
- Password: `admin123`

On first successful login, this account must change its password before the main window opens.

After that, password updates are available from:

`Account -> Profile & Password`

## Admin Safeguards

- The built-in `Administrator` role is protected and cannot be edited into a broken state
- The original bootstrap admin user is protected and cannot have its role changed or be deactivated
- Other admin-capable users can manage and demote one another, and can demote themselves, as long as at least one active admin-capable user remains
- If the current user changes their own role, menus and action buttons refresh immediately to match the new permissions

## Local App Data

By default, runtime data is stored outside the repository in:

- database: `~/.task_app/task_app.db`
- attachments: `~/.task_app/attachments`
- exports: `~/.task_app/exports`
- local app key file: `~/.task_app/secret.key`

This keeps runtime data and project source code separated.

## Development Notes

- The repository should not include runtime data, local secrets, or the virtual environment
- A `.gitignore` is included for safe GitHub publishing
- The test suite can be run with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Packaging

This project includes a macOS app build flow using `PyInstaller` inside the local `.venv`.

Install build dependencies into `.venv`:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pyinstaller
```

Run the test suite:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test*.py'
```

Build the `.app` bundle:

```bash
chmod +x scripts/build_macos_app.sh
./scripts/build_macos_app.sh
```

Output:

```text
dist/Python Task Manager.app
```

The build script also generates the app icon assets inside:

```text
assets/icon/
```

Notes:

- Packaging is intended to be run on macOS
- Build artifacts are ignored by Git via `.gitignore`
- The generated `.app` uses the bundle identifier:
  `com.aalnajim.python-task-manager`

## Version Control Notes

Keep these tracked in Git:

- source code
- tests
- `README.md`
- `requirements.txt`
- packaging scripts

Do not commit:

- `.venv/`
- `build/`
- `dist/`
- local runtime data from `~/.task_app`

## Releases

Download packaged app builds from the [GitHub Releases](https://github.com/aalnajim/python-task-manager/releases) page.

Current macOS release:

- [Python Task Manager v1.0.0](https://github.com/aalnajim/python-task-manager/releases/tag/v1.0.0)

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE).
