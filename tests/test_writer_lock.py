"""Tests for Single-writer lock (D39.4) and UI disable logic."""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest

from sr_agent.store.writer_lock import acquire, holder, release
from tools import sr_run
from ui.app import is_write_disabled


class TestWriterLock:
    def test_double_acquire_same_process(self, tmp_path):
        lock_file = tmp_path / ".sr_writer.lock"

        # 1st acquire succeeds
        assert acquire("orchestrator", path=lock_file) is True

        # Check holder info
        info = holder(lock_file)
        assert info is not None
        assert info["role"] == "orchestrator"
        assert info["pid"] == os.getpid()

        # 2nd acquire in same process fails
        assert acquire("heal", path=lock_file) is False

        # Cleanup
        release(lock_file)
        assert holder(lock_file) is None
        assert not lock_file.exists()

    def test_orphan_lock_cleanup_and_reacquire(self, tmp_path):
        lock_file = tmp_path / ".sr_writer.lock"

        # Write a lock file with a non-existent PID
        fake_pid = 999999
        # Ensure fake_pid is truly dead
        try:
            os.kill(fake_pid, 0)
            pytest.skip("PID 999999 unexpectedly exists")
        except ProcessLookupError:
            pass

        lock_file.write_text(
            f'{{"role": "dead_worker", "pid": {fake_pid}, "started_at": "2026-07-19T00:00:00Z"}}',
            encoding="utf-8",
        )
        assert lock_file.exists()

        # holder() detects dead PID, unlinks orphan lock, returns None
        assert holder(lock_file) is None
        assert not lock_file.exists()

        # Subsequent acquire succeeds
        assert acquire("orchestrator", path=lock_file) is True
        info = holder(lock_file)
        assert info is not None
        assert info["role"] == "orchestrator"

        release(lock_file)

    def test_sr_run_releases_in_finally_on_exception(self, tmp_path):
        lock_file = tmp_path / ".sr_writer.lock"

        with patch("sr_agent.store.writer_lock.DEFAULT_LOCK_PATH", lock_file):
            with patch("tools.sr_run.run_pipeline", side_effect=RuntimeError("Phase crash")):
                # Run sr_run with arguments that reach run_pipeline
                with pytest.raises(RuntimeError, match="Phase crash"):
                    sr_run.main(["run", "--query", "test"])

                # Ensure lock was released in finally despite exception
                assert holder(lock_file) is None
                assert not lock_file.exists()

    def test_is_write_disabled_pure_function(self):
        # Case 1: No lock held -> writes enabled (False)
        assert is_write_disabled(None, current_pid=100) is False
        assert is_write_disabled(None) is False

        # Case 2: Lock held by another PID -> writes disabled (True)
        other_holder = {"role": "orchestrator", "pid": 9999, "started_at": "2026-07-19T10:00:00Z"}
        assert is_write_disabled(other_holder, current_pid=100) is True

        # Case 3: Lock held by current PID -> writes enabled (False)
        same_holder = {"role": "ui", "pid": 100, "started_at": "2026-07-19T10:00:00Z"}
        assert is_write_disabled(same_holder, current_pid=100) is False

        # Case 4: Lock held without current_pid specified -> writes disabled (True)
        assert is_write_disabled(other_holder) is True


# --- Test đối kháng của PM (luật Oracle — audit R1 + defect late-binding) -------------


class TestWriterLockHardening:
    def test_stale_lock_over_age_ceiling_self_cleans(self, tmp_path):
        """R1 (PID-reuse): PID 'sống' nhưng lock quá trần tuổi = xác đội lốt — phải tự dọn.

        Dùng chính PID của test (chắc chắn sống) với started_at 7h trước:
        nếu chỉ check os.kill thì lock này bất tử — hệ khóa chết vĩnh viễn.
        """
        from datetime import datetime, timedelta, timezone

        lock_file = tmp_path / ".sr_writer.lock"
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        lock_file.write_text(
            f'{{"role": "zombie", "pid": {os.getpid()}, "started_at": "{old_ts}"}}',
            encoding="utf-8",
        )

        assert holder(lock_file) is None
        assert not lock_file.exists()
        assert acquire("orchestrator", path=lock_file) is True
        release(lock_file)

    def test_fresh_alive_lock_is_not_cleaned(self, tmp_path):
        """Chiều ngược của R1: lock tươi + PID sống KHÔNG được dọn oan."""
        lock_file = tmp_path / ".sr_writer.lock"
        assert acquire("orchestrator", path=lock_file) is True

        info = holder(lock_file)
        assert info is not None
        assert info["role"] == "orchestrator"
        assert lock_file.exists()
        release(lock_file)

    def test_default_path_is_late_bound(self, tmp_path):
        """Defect fix: patch DEFAULT_LOCK_PATH phải có tác dụng thật.

        Trước fix, default param bind lúc import ⇒ test sr_run ở trên xanh nhưng RỖNG
        (assert trên file chưa bao giờ được tạo, còn code thật ghi vào staging/ thật).
        """
        lock_file = tmp_path / "patched.lock"
        with patch("sr_agent.store.writer_lock.DEFAULT_LOCK_PATH", lock_file):
            assert acquire("orchestrator") is True
            assert lock_file.exists()

            info = holder()
            assert info is not None
            assert info["pid"] == os.getpid()

            release()
            assert not lock_file.exists()
