import logging
from collections.abc import Callable
from threading import Event

import velopack

from src.utils.project_paths import PROJECT_ROOT

REPOSITORY_URL = "https://github.com/Valentin-alix/AstraBot"
logger = logging.getLogger(__name__)


def prepare_update(progress: Callable[[str], None], cancelled: Event) -> bool:
    if not (PROJECT_ROOT / "sq.version").is_file() or cancelled.is_set():
        return False

    try:
        manager = velopack.UpdateManager(velopack.GithubSource(REPOSITORY_URL))
        progress("Checking for updates...")
        update = manager.check_for_updates()
        if update is None or cancelled.is_set():
            return False
        progress("Downloading update...")
        manager.download_updates(update, lambda percent: progress(f"Downloading update... {percent}%"))
        if cancelled.is_set():
            return False
        progress("Installing update and restarting...")
        manager.wait_exit_then_apply_updates(update)
        return True
    except (RuntimeError, OSError):
        logger.warning("Update failed; continuing with the current installation", exc_info=True)
        return False
