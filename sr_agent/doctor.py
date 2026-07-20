"""Kiểm tra tiền vận hành (preflight) cho máy chạy SR-Agent.

Chạy: python -m sr_agent.pipeline doctor

Hai mức check:
- REQUIRED: fail là pipeline không chạy được -> exit code 1 (để script setup /
  launchd installer gate được).
- OPTIONAL: fail chỉ làm mất một tính năng (Ollama, IEEE, Notion) — pipeline
  vẫn chạy ở chế độ suy giảm tương ứng; không đổi exit code.
"""

from __future__ import annotations

import enum
import importlib.util
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sr_agent import config

CORE_DEPS = ("pydantic", "rapidfuzz", "httpx", "tenacity", "feedparser",
             "dotenv", "notion_client")


class Level(enum.Enum):
    REQUIRED = "BẮT BUỘC"
    OPTIONAL = "TÙY CHỌN"


@dataclass(frozen=True)
class CheckResult:
    name: str
    level: Level
    ok: bool
    detail: str
    fix_hint: str = ""


# --- các check REQUIRED --------------------------------------------------------

def check_python() -> CheckResult:
    ok = sys.version_info >= (3, 11)
    return CheckResult(
        "Python >= 3.11", Level.REQUIRED, ok,
        f"đang chạy {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        fix_hint="uv venv .venv --python 3.11 rồi cài lại dependencies",
    )


def check_core_deps() -> CheckResult:
    missing = [d for d in CORE_DEPS if importlib.util.find_spec(d) is None]
    return CheckResult(
        "Dependencies lõi", Level.REQUIRED, not missing,
        "đủ " + ", ".join(CORE_DEPS) if not missing else "thiếu " + ", ".join(missing),
        fix_hint='uv pip install -p .venv/bin/python -e ".[ui,dev]"',
    )


def check_storage_writable(db_path: Path | None = None) -> CheckResult:
    db_path = db_path or config.DB_PATH
    quarantine = db_path.parent / "quarantine"
    try:
        for target in (db_path.parent, quarantine):
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".doctor-{uuid.uuid4().hex}"
            probe.write_text("ok")
            probe.unlink()
    except OSError as exc:
        return CheckResult(
            "Staging ghi được", Level.REQUIRED, False,
            f"không ghi được {db_path.parent}: {exc}",
            fix_hint="kiểm tra quyền thư mục hoặc đổi SR_AGENT_DB trong .env",
        )
    return CheckResult(
        "Staging ghi được", Level.REQUIRED, True, f"{db_path.parent} + quarantine/ OK"
    )


# --- các check OPTIONAL --------------------------------------------------------

def check_ollama(client=None) -> list[CheckResult]:
    """2 kết quả: server sống + model đã pull. Server chết -> model coi như thiếu."""
    from sr_agent.parser.ollama_client import OllamaClient

    client = client or OllamaClient()
    if not client.is_available():
        return [
            CheckResult(
                "Ollama server", Level.OPTIONAL, False,
                f"không phản hồi tại {client.base_url}",
                fix_hint="mở app Ollama (hoặc `ollama serve`); thiếu Ollama pipeline "
                         "vẫn chạy phần tất định, chỉ mất LLM parse",
            ),
            CheckResult(
                f"Model {client.model}", Level.OPTIONAL, False,
                "chưa kiểm tra được (server không phản hồi)",
                fix_hint=f"ollama pull {client.model}",
            ),
        ]
    tags = client.list_models()
    has_model = any(t == client.model or t.startswith(client.model + ":") for t in tags)
    return [
        CheckResult("Ollama server", Level.OPTIONAL, True, f"OK tại {client.base_url}"),
        CheckResult(
            f"Model {client.model}", Level.OPTIONAL, has_model,
            "đã pull" if has_model else f"chưa có trong {len(tags)} model đã pull",
            fix_hint=f"ollama pull {client.model}",
        ),
    ]


def check_ieee_key() -> CheckResult:
    ok = bool(config.IEEE_API_KEY)
    return CheckResult(
        "IEEE_API_KEY", Level.OPTIONAL, ok,
        "đã cấu hình" if ok else "chưa có — không fetch được IEEE Xplore thật",
        fix_hint="đăng ký miễn phí tại developer.ieee.org rồi điền vào .env",
    )


def check_notion() -> CheckResult:
    ok = bool(config.NOTION_TOKEN) and bool(config.NOTION_PARENT_PAGE_ID)
    if bool(config.NOTION_TOKEN) != bool(config.NOTION_PARENT_PAGE_ID):
        detail = "chỉ có 1 trong 2 biến (cần cả NOTION_TOKEN lẫn NOTION_PARENT_PAGE_ID)"
    else:
        detail = "đã cấu hình" if ok else "chưa có — Approve sẽ chạy dry-run (APPROVED_LOCAL)"
    return CheckResult(
        "Notion", Level.OPTIONAL, ok, detail,
        fix_hint="tạo internal integration tại notion.so/my-integrations, share trang "
                 "cha cho integration, điền 2 biến vào .env",
    )


def check_streamlit() -> CheckResult:
    ok = importlib.util.find_spec("streamlit") is not None
    return CheckResult(
        "Streamlit (QC UI)", Level.OPTIONAL, ok,
        "cài rồi" if ok else "chưa cài — không mở được ui/app.py",
        fix_hint='uv pip install -p .venv/bin/python -e ".[ui]"',
    )


def check_model_digests(client=None) -> CheckResult:
    import json
    from sr_agent.parser.ollama_client import OllamaClient
    
    lock_path = Path(__file__).resolve().parent.parent / "tools" / "profiles" / "models.lock.json"
    if not lock_path.exists():
        return CheckResult(
            "Model digests", Level.OPTIONAL, True,
            "bỏ qua (không tìm thấy models.lock.json)"
        )
    
    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
        locked_models = lock_data.get("models", {})
    except Exception as exc:
        return CheckResult(
            "Model digests", Level.OPTIONAL, False,
            f"lỗi đọc lockfile: {exc}",
            fix_hint="kiểm tra định dạng file tools/profiles/models.lock.json"
        )
        
    client = client or OllamaClient()
    if not client.is_available():
        return CheckResult(
            "Model digests", Level.OPTIONAL, False,
            "không kiểm tra được (server không phản hồi)",
            fix_hint="mở Ollama server"
        )
        
    digests = client.get_model_digests()
    
    mismatches = []
    missing_models = []
    
    for model_name, expected_digest in locked_models.items():
        actual_digest = digests.get(model_name)
        if not actual_digest:
            found = False
            for act_name, act_dig in digests.items():
                if act_name == model_name or act_name.startswith(model_name + ":") or model_name.startswith(act_name + ":"):
                    actual_digest = act_dig
                    found = True
                    break
            if not found:
                missing_models.append(model_name)
                continue
                
        if actual_digest != expected_digest:
            mismatches.append(f"{model_name} (actual={actual_digest[:8]}... vs expected={expected_digest[:8]}...)")
            
    if missing_models or mismatches:
        detail = []
        if missing_models:
            detail.append(f"thiếu model {', '.join(missing_models)}")
        if mismatches:
            detail.append(f"lệch digest: {', '.join(mismatches)}")
        
        return CheckResult(
            "Model digests", Level.OPTIONAL, False,
            "CẢNH BÁO: " + "; ".join(detail),
            fix_hint="ollama pull lại model bị lệch hoặc cập nhật lockfile"
        )
        
    return CheckResult(
        "Model digests", Level.OPTIONAL, True,
        "tất cả model khớp digest trong lockfile"
    )


def check_model_drift(store, batch_uid: str, client) -> None:
    import json
    lock_path = Path(__file__).resolve().parent.parent / "tools" / "profiles" / "models.lock.json"
    if not lock_path.exists():
        return
    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
        locked_models = lock_data.get("models", {})
    except Exception:
        return
    
    if not client or not hasattr(client, "get_model_digests"):
        return
        
    digests = client.get_model_digests()
    for model_name, expected_digest in locked_models.items():
        actual_digest = digests.get(model_name)
        if not actual_digest:
            for act_name, act_dig in digests.items():
                if act_name == model_name or act_name.startswith(model_name + ":") or model_name.startswith(act_name + ":"):
                    actual_digest = act_dig
                    break
        if actual_digest and actual_digest != expected_digest:
            store.log_event(
                batch_uid,
                "MODEL_DRIFT",
                f"{model_name}: {expected_digest} -> {actual_digest}"
            )


def run_checks(db_path: Path | None = None, ollama_client=None) -> list[CheckResult]:
    results = [check_python(), check_core_deps(), check_storage_writable(db_path)]
    results += check_ollama(ollama_client)
    results.append(check_model_digests(ollama_client))
    results += [check_ieee_key(), check_notion(), check_streamlit()]
    return results


def render(results: list[CheckResult]) -> int:
    """In bảng kết quả, trả exit code (0 = mọi REQUIRED pass)."""
    for r in results:
        mark = "✓" if r.ok else ("✗" if r.level is Level.REQUIRED else "–")
        print(f"{mark} [{r.level.value}] {r.name}: {r.detail}")
        if not r.ok and r.fix_hint:
            print(f"    ↳ khắc phục: {r.fix_hint}")
    required_fail = [r for r in results if r.level is Level.REQUIRED and not r.ok]
    optional_fail = [r for r in results if r.level is Level.OPTIONAL and not r.ok]
    if required_fail:
        print(f"\nKẾT LUẬN: {len(required_fail)} check BẮT BUỘC fail — chưa chạy được pipeline.")
        return 1
    note = f" ({len(optional_fail)} tính năng tùy chọn chưa bật)" if optional_fail else ""
    print(f"\nKẾT LUẬN: sẵn sàng chạy pipeline{note}.")
    return 0


def main() -> int:
    return render(run_checks())
