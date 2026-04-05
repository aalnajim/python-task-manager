# Python Task Manager

Local-first desktop task manager built with Python, PySide6, and SQLite, designed for macOS and structured so it can later be packaged as a `.app`.

## Highlights

- Desktop UI built with `PySide6`
- Local multi-user task management
- Admin and user roles
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

- `admin` users can:
  - create users
  - activate and deactivate users
  - assign and reassign tasks
  - edit and delete any task
- regular users can:
  - create tasks
  - edit their own tasks
  - change status on tasks they participate in
- owners can delete their own tasks only while those tasks are still unassigned

### Import and Export

- Export task data to:
  - `JSON` bundle with attachment files
  - `CSV` for spreadsheet/reporting workflows
- Import tasks from a JSON bundle

### Security

- Passwords are stored using salted `PBKDF2-SHA256`
- Task content is encrypted at rest
- Task decryption follows per-user access rules
- Task access is intended for:
  - the creator
  - the assignee
  - active admins

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

## Default Local Admin

Initial local development credentials:

- Username: `admin`
- Password: `admin123`

Change the password after first login from:

`Account -> Profile & Password`

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

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE).
