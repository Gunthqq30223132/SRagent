"""Single-writer lock (D39.4) — cơ chế khóa cộng tác 1-writer cho staging DB.

TẠI SAO: WAL của SQLite giúp DB không hỏng dữ liệu khi ghi đồng thời, nhưng
interleaving giữa orchestrator batch, UI approve/reject, hoặc heal job có thể
tạo ra trạng thái không nhất quán. Lock này đảm bảo chỉ có 1 tiến trình được
phép thực hiện phiên ghi.

NGUYÊN TẮC:
- acquire(role): atomic file creation (`open(..., "x")`) ghi JSON {role, pid, started_at}.
- holder(): tự dọn lock mồ côi nếu PID trong lock đã chết (os.kill(pid, 0) raise ProcessLookupError).
- release(): xóa file lock khi xong.
- UI KHÔNG bao giờ acquire lock, chỉ đọc holder() để hiển thị banner cảnh báo và disable nút ghi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOCK_PATH = Path("staging/.sr_writer.lock")

# Trần tuổi lock (chống PID-reuse): macOS có thể cấp lại PID cũ cho tiến trình khác,
# khiến lock mồ côi trông như đang sống và hệ khóa chết vĩnh viễn. Batch thật dài
# nhất tính bằng phút/doc — lock sống quá trần này chắc chắn là xác.
MAX_LOCK_AGE_HOURS = 6


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _resolve(path: Path | str | None) -> Path:
    # Late-binding: đọc DEFAULT_LOCK_PATH tại thời điểm GỌI, không phải lúc import —
    # để test patch được default và mọi caller cùng nhìn một đường dẫn.
    return Path(path) if path is not None else DEFAULT_LOCK_PATH


def holder(path: Path | str | None = None) -> dict[str, Any] | None:
    """Đọc thông tin holder từ file lock. Tự dọn lock mồ côi nếu PID đã chết."""
    lock_file = _resolve(path)
    if not lock_file.exists():
        return None

    try:
        content = lock_file.read_text(encoding="utf-8")
        data = json.loads(content)
        pid = int(data["pid"])
        role = str(data["role"])
        started_at = str(data.get("started_at", ""))
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        # File hỏng hoặc không đúng format -> dọn dẹp và coi như không có holder
        lock_file.unlink(missing_ok=True)
        return None

    if not _is_pid_alive(pid):
        # Lock mồ côi (PID đã chết) -> xóa lock file và trả về None
        lock_file.unlink(missing_ok=True)
        return None

    # PID-reuse guard: PID "sống" nhưng lock quá trần tuổi = xác đội lốt.
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(started_at)
        if age.total_seconds() > MAX_LOCK_AGE_HOURS * 3600:
            lock_file.unlink(missing_ok=True)
            return None
    except ValueError:
        # started_at không parse được — cùng họ file hỏng, dọn như trên
        lock_file.unlink(missing_ok=True)
        return None

    return {"role": role, "pid": pid, "started_at": started_at}


def acquire(role: str, path: Path | str | None = None) -> bool:
    """Tạo lock file atomically.

    Nếu lock file đã tồn tại:
      - holder() tự dọn nếu lock mồ côi (PID đã chết).
      - Nếu holder() trả về None sau khi dọn, thử lại 1 lần nữa.
      - Ngược lại (có tiến trình sống đang giữ lock), trả về False.
    """
    lock_file = _resolve(path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    def _try_create() -> bool:
        try:
            with lock_file.open("x", encoding="utf-8") as fh:
                payload = {
                    "role": role,
                    "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            return True
        except FileExistsError:
            return False

    if _try_create():
        return True

    # Nếu thất bại do FileExistsError, kiểm tra xem có phải lock mồ côi không
    if holder(lock_file) is None:
        # Lock mồ côi đã được holder() dọn dẹp -> thử lại lần 2
        return _try_create()

    return False


def release(path: Path | str | None = None) -> None:
    """Giải phóng lock file."""
    lock_file = _resolve(path)
    lock_file.unlink(missing_ok=True)
