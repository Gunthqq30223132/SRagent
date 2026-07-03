import httpx
import pytest
import respx

from sr_agent import config
from sr_agent.doctor import (
    Level,
    check_ieee_key,
    check_notion,
    check_ollama,
    check_storage_writable,
    render,
    run_checks,
)
from sr_agent.parser.ollama_client import OllamaClient

OLLAMA = "http://testollama:11434"


def fake_client() -> OllamaClient:
    return OllamaClient(base_url=OLLAMA)


class TestOllamaChecks:
    @respx.mock
    def test_server_up_and_model_pulled(self):
        respx.get(f"{OLLAMA}/api/tags").mock(
            return_value=httpx.Response(
                200, json={"models": [{"name": "qwen2.5:7b-instruct"}, {"name": "gemma3:4b"}]}
            )
        )
        server, model = check_ollama(fake_client())
        assert server.ok and model.ok

    @respx.mock
    def test_server_up_model_missing(self):
        respx.get(f"{OLLAMA}/api/tags").mock(
            return_value=httpx.Response(200, json={"models": [{"name": "llama3:latest"}]})
        )
        server, model = check_ollama(fake_client())
        assert server.ok
        assert not model.ok
        assert "ollama pull" in model.fix_hint

    @respx.mock
    def test_server_down_both_fail_but_optional(self):
        respx.get(f"{OLLAMA}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        results = check_ollama(fake_client())
        assert all(not r.ok for r in results)
        assert all(r.level is Level.OPTIONAL for r in results)


class TestEnvChecks:
    def test_missing_keys_are_optional(self, monkeypatch):
        monkeypatch.setattr(config, "IEEE_API_KEY", "")
        monkeypatch.setattr(config, "NOTION_TOKEN", "")
        monkeypatch.setattr(config, "NOTION_PARENT_PAGE_ID", "")
        for r in (check_ieee_key(), check_notion()):
            assert not r.ok
            assert r.level is Level.OPTIONAL

    def test_notion_needs_both_vars(self, monkeypatch):
        monkeypatch.setattr(config, "NOTION_TOKEN", "secret")
        monkeypatch.setattr(config, "NOTION_PARENT_PAGE_ID", "")
        r = check_notion()
        assert not r.ok
        assert "1 trong 2" in r.detail


class TestStorage:
    def test_writable_tmp_path_passes(self, tmp_path):
        assert check_storage_writable(tmp_path / "staging" / "db.sqlite").ok

    def test_unwritable_parent_fails_required(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("một file chắn chỗ thư mục")  # mkdir lên file -> OSError
        r = check_storage_writable(blocker / "db.sqlite")
        assert not r.ok
        assert r.level is Level.REQUIRED


class TestExitCode:
    @respx.mock
    def test_optional_failures_keep_exit_zero(self, tmp_path, monkeypatch, capsys):
        # môi trường CI: không Ollama, không key nào — vẫn phải "sẵn sàng chạy"
        respx.get(f"{OLLAMA}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        monkeypatch.setattr(config, "IEEE_API_KEY", "")
        monkeypatch.setattr(config, "NOTION_TOKEN", "")
        monkeypatch.setattr(config, "NOTION_PARENT_PAGE_ID", "")
        results = run_checks(db_path=tmp_path / "db.sqlite", ollama_client=fake_client())
        assert render(results) == 0
        out = capsys.readouterr().out
        assert "sẵn sàng chạy pipeline" in out
        assert "–" in out  # optional fail đánh dấu –, không phải ✗

    def test_required_failure_exits_one(self, tmp_path, capsys):
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        results = [check_storage_writable(blocker / "db.sqlite")]
        assert render(results) == 1
        assert "BẮT BUỘC fail" in capsys.readouterr().out


class TestCLI:
    def test_doctor_subcommand_registered(self, capsys):
        from sr_agent.pipeline import main

        code = main(["doctor"])
        assert code in (0, 1)
        assert "KẾT LUẬN" in capsys.readouterr().out
