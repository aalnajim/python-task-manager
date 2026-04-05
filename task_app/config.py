from __future__ import annotations

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


def get_app_paths() -> AppPaths:
    home = Path.home()
    base_dir = home / ".task_app"
    attachments_dir = base_dir / "attachments"
    exports_dir = base_dir / "exports"
    key_path = base_dir / "secret.key"
    db_path = base_dir / "task_app.db"
    for path in (base_dir, attachments_dir, exports_dir):
        path.mkdir(parents=True, exist_ok=True)
    return AppPaths(
        base_dir=base_dir,
        db_path=db_path,
        attachments_dir=attachments_dir,
        exports_dir=exports_dir,
        key_path=key_path,
    )
