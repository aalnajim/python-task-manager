from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "TaskApp"


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path
    db_path: Path
    attachments_dir: Path
    exports_dir: Path
    key_path: Path
    login_state_path: Path


def get_app_paths() -> AppPaths:
    home = Path.home()
    base_dir = home / ".task_app"
    attachments_dir = base_dir / "attachments"
    exports_dir = base_dir / "exports"
    key_path = base_dir / "secret.key"
    db_path = base_dir / "task_app.db"
    login_state_path = base_dir / "login_state.json"
    for path in (base_dir, attachments_dir, exports_dir):
        path.mkdir(parents=True, exist_ok=True)
    return AppPaths(
        base_dir=base_dir,
        db_path=db_path,
        attachments_dir=attachments_dir,
        exports_dir=exports_dir,
        key_path=key_path,
        login_state_path=login_state_path,
    )


class LoginStateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return {"remember_me": False, "username": ""}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"remember_me": False, "username": ""}
        return {
            "remember_me": bool(data.get("remember_me")),
            "username": str(data.get("username", "")),
        }

    def save(self, remember_me: bool, username: str) -> None:
        payload = {
            "remember_me": remember_me,
            "username": username.strip() if remember_me else "",
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
