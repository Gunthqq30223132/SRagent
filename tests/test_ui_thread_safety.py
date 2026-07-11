"""Guard chống tái phạm bug SQLite chéo thread trong UI (2026-07-11).

Streamlit chạy lại script trên thread KHÁC NHAU ở mỗi rerun. Bất kỳ cơ chế cache nào
giữ StagingStore (kèm sqlite3.Connection) sống xuyên rerun đều nổ
`sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in
that same thread` — đúng cú Approve thật đầu tiên của con người mới lộ ra (script
giả lập của executor không đi qua đường rerun nên không bao giờ thấy).

Luật: UI mở StagingStore MỚI theo từng rerun; cấm cache connection.
"""

from pathlib import Path

UI_APP = Path(__file__).resolve().parent.parent / "ui" / "app.py"


class TestUIThreadSafety:
    def test_ui_does_not_cache_sqlite_store(self):
        src = UI_APP.read_text(encoding="utf-8")
        # cache_resource/cache_data giữ object xuyên rerun-thread — cấm trong app.py
        # chừng nào StagingStore còn ôm sqlite3.Connection tạo-tại-thread.
        assert "cache_resource" not in src, (
            "ui/app.py cache một resource xuyên rerun — nếu resource đó là StagingStore/"
            "sqlite3.Connection sẽ tái phạm bug chéo thread 2026-07-11. Mở store theo "
            "từng rerun, hoặc chứng minh resource được cache không ôm connection."
        )
        assert "StagingStore()" in src   # store vẫn phải được khởi tạo trực tiếp per-rerun

    def test_store_usable_when_created_in_worker_thread(self, tmp_path):
        """Mô phỏng rerun: mỗi thread tự mở store của mình — phải chạy sạch."""
        import threading

        from sr_agent.store.staging import StagingStore

        db = tmp_path / "t.db"
        errors: list[Exception] = []

        def rerun():
            try:
                with StagingStore(db) as store:      # store mở TRONG thread của rerun
                    store.purge_expired()            # đúng call đã nổ ở bug gốc
            except Exception as exc:                 # pragma: no cover - chỉ khi fail
                errors.append(exc)

        for _ in range(3):                           # 3 "rerun" nối tiếp, thread khác nhau
            t = threading.Thread(target=rerun)
            t.start()
            t.join()

        assert errors == []
