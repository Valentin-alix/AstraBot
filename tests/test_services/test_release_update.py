from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from src.services import release_update


def test_bundle_without_manifest_skips_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_update, "PROJECT_ROOT", tmp_path)
    manager = Mock()
    monkeypatch.setattr(release_update.velopack, "UpdateManager", manager)

    assert not release_update.prepare_update(Mock(), Event())
    manager.assert_not_called()


@pytest.mark.parametrize("download_fails", [False, True])
def test_update_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, download_fails: bool
) -> None:
    (tmp_path / "sq.version").touch()
    monkeypatch.setattr(release_update, "PROJECT_ROOT", tmp_path)
    manager = Mock()
    monkeypatch.setattr(release_update.velopack, "UpdateManager", lambda _: manager)
    if download_fails:
        manager.download_updates.side_effect = RuntimeError("download interrupted")

    assert release_update.prepare_update(Mock(), Event()) is not download_fails
    if download_fails:
        manager.wait_exit_then_apply_updates.assert_not_called()
    else:
        manager.wait_exit_then_apply_updates.assert_called_once_with(manager.check_for_updates.return_value)
