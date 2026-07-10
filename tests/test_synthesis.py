"""Tests cho tools/synthesis/ — SynthesisProvider + NotebookLMExporter. Offline 100%.

Ollama được mock hoàn toàn bằng respx (không chạm mạng). Các "secret" trong file là
chuỗi giả có chủ đích (FAKE) — tồn tại để chứng minh interceptor bắt được, không phải
credential thật (cùng quy ước tests/test_guards.py).
"""

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from sr_agent.models.schemas import CritiqueQuestion, Document
from sr_agent.parser.ollama_client import OllamaClient
from sr_agent.store.staging import StagingStore
from tools.guard.outbound import OutboundViolation, scan
from tools.synthesis import provider as P
from tools.synthesis.exporter import ExporterError, build_bundle
from tools.synthesis.provider import (
    CloudNotAllowedError,
    OllamaSynthesisProvider,
    ProviderUnavailable,
    SourceDoc,
    SynthesisResult,
    get_provider,
    synthesize,
)

OLLAMA = "http://testollama:11434"

# Nguồn Layer A với hằng số số học THẬT — firewall đối chiếu nguyên văn với nó.
SRC_MD = (
    "The system listens on port 8080 and reaches 99.9% accuracy using "
    "O(n log n) preprocessing at 12 ms latency (v2.1.0)."
)
SOURCES = [SourceDoc(uid="ieee:12345678", markdown=SRC_MD, source_map_entry="IEEE 8080")]

FIXED_TS = datetime(2026, 7, 10, 8, 30, 0, tzinfo=timezone.utc)


def _mock_tags_ok() -> None:
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:7b-instruct"}]})
    )


def _mock_tags_dead() -> None:
    respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(500))


def _mock_chat(answer: str, citations: list[str]) -> None:
    content = json.dumps({"answer": answer, "citations": citations})
    respx.post(f"{OLLAMA}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"role": "assistant", "content": content}})
    )


def _ollama_provider() -> OllamaSynthesisProvider:
    return OllamaSynthesisProvider(client=OllamaClient(base_url=OLLAMA))


# --- Provider: firewall gate --------------------------------------------------


class TestOllamaSynthesisFirewall:
    @respx.mock
    def test_clean_answer_passes_firewall(self):
        _mock_tags_ok()
        answer = "The system uses O(n log n) preprocessing on port 8080 with 99.9% accuracy."
        _mock_chat(answer, ["ieee:12345678"])
        result = _ollama_provider().synthesize("How does it perform?", SOURCES)
        assert isinstance(result, SynthesisResult)
        assert result.provider == "ollama"
        assert result.firewall.passed is True
        assert result.citations == ["ieee:12345678"]
        assert result.is_valid is True

    @respx.mock
    def test_fabricated_numbers_yield_void_verdict_without_rewriting(self):
        _mock_tags_ok()
        fabricated = "The system reaches 99.8% accuracy on port 9090."  # cả hai đều bịa
        _mock_chat(fabricated, ["ieee:12345678"])
        result = _ollama_provider().synthesize("q", SOURCES)
        assert result.firewall.passed is False
        assert result.is_valid is False
        # verifier KHÔNG "sửa cho khớp" — văn bản gốc giữ nguyên
        assert result.text == fabricated
        flagged = " ".join(v.reason for v in result.firewall.violations)
        assert "99.8%" in flagged and "9090" in flagged

    @respx.mock
    def test_empty_citations_makes_result_invalid_even_if_firewall_passes(self):
        _mock_tags_ok()
        _mock_chat("A purely qualitative summary with no technical constants.", [])
        result = _ollama_provider().synthesize("q", SOURCES)
        assert result.firewall.passed is True
        assert result.citations == []
        assert result.is_valid is False


# --- Provider: registry & chính sách bất đối xứng -----------------------------


class TestRegistryAsymmetricPolicy:
    def test_registry_defaults_to_local_ollama(self, monkeypatch):
        monkeypatch.delenv("SR_SYNTH_PROVIDER", raising=False)
        monkeypatch.delenv("SR_ALLOW_CLOUD", raising=False)
        prov = get_provider()
        assert prov.name == "ollama"
        assert prov.is_local is True

    def test_registry_refuses_cloud_without_flag(self, monkeypatch):
        monkeypatch.delenv("SR_ALLOW_CLOUD", raising=False)
        with pytest.raises(CloudNotAllowedError):
            get_provider("gemini")

    def test_env_selecting_cloud_still_blocked_without_opt_in(self, monkeypatch):
        monkeypatch.setenv("SR_SYNTH_PROVIDER", "gemini")
        monkeypatch.delenv("SR_ALLOW_CLOUD", raising=False)
        with pytest.raises(CloudNotAllowedError):
            get_provider()

    def test_explicit_allow_cloud_unblocks_but_provider_is_not_local(self, monkeypatch):
        monkeypatch.delenv("SR_ALLOW_CLOUD", raising=False)
        prov = get_provider("gemini", allow_cloud=True)
        assert prov.is_local is False
        assert prov.name == "gemini"

    def test_env_allow_cloud_flag_is_an_explicit_opt_in(self, monkeypatch):
        monkeypatch.setenv("SR_ALLOW_CLOUD", "1")
        prov = get_provider("gemini")
        assert prov.is_local is False


# --- Provider: fallback bất đối xứng (cloud→local TỰ ĐỘNG, local→cloud KHÔNG) ---


class TestAsymmetricFallback:
    @respx.mock
    def test_dead_ollama_raises_clearly_and_never_switches_to_cloud(self):
        _mock_tags_dead()
        prov = _ollama_provider()
        with pytest.raises(ProviderUnavailable) as exc:
            prov.synthesize("q", SOURCES)
        assert "cloud" in str(exc.value).lower()  # nêu rõ KHÔNG tự nhảy cloud

    @respx.mock
    def test_local_failure_never_auto_falls_back_to_cloud(self, monkeypatch):
        monkeypatch.delenv("SR_SYNTH_PROVIDER", raising=False)
        _mock_tags_dead()
        with pytest.raises(ProviderUnavailable):
            synthesize("q", SOURCES, client=OllamaClient(base_url=OLLAMA))

    @respx.mock
    def test_cloud_failure_auto_falls_back_to_local(self, monkeypatch):
        _mock_tags_ok()
        _mock_chat("Uses O(n log n) on port 8080 at 99.9% accuracy.", ["ieee:12345678"])

        class _FlakyCloud:
            name = "flakycloud"
            is_local = False

            def is_available(self):
                return False

            def synthesize(self, question, sources, schema_model=None):
                raise ProviderUnavailable("cloud quota exhausted")

        monkeypatch.setitem(
            P._REGISTRY,
            "flakycloud",
            P._ProviderSpec(is_local=False, factory=lambda **kw: _FlakyCloud()),
        )
        result = synthesize(
            "q", SOURCES, provider="flakycloud", allow_cloud=True,
            client=OllamaClient(base_url=OLLAMA),
        )
        assert result.provider == "ollama"  # đã tự lui về local
        assert result.firewall.passed is True


# --- Exporter: NotebookLM bundle ---------------------------------------------


def _seed(tmp_path, doc: Document):
    db = tmp_path / "t.db"
    with StagingStore(db) as store:
        store.upsert(doc)
    return db


class TestNotebookLMExporter:
    def test_builds_clean_bundle_all_files_pass_scan(self, tmp_path):
        doc = Document(
            uid="", source="arxiv", source_id="arxiv:2401.12345", authority_tier=2,
            title="Efficient Retrieval", abstract="We evaluate on GLUE with 10000 samples.",
            authors=["Ada Lovelace"],
            critique_questions=[CritiqueQuestion(question="Why exclude decoder models?")],
        )
        db = _seed(tmp_path, doc)
        bundle = build_bundle(
            [doc.uid], db, exports_root=tmp_path / "exports",
            question="What are the trade-offs?", now=FIXED_TS,
        )
        assert bundle.exists()
        names = {p.name for p in bundle.iterdir()}
        assert {"README.md", "SOURCE_MAP.md", "QUESTIONS.md"} <= names
        assert "arxiv_2401.12345.md" in names
        # câu hỏi phản biện + câu hỏi trọng tâm có trong QUESTIONS.md
        questions = (bundle / "QUESTIONS.md").read_text()
        assert "Why exclude decoder models?" in questions
        assert "What are the trade-offs?" in questions
        # bất biến: MỌI file trong bundle sạch outbound
        for p in bundle.iterdir():
            assert scan(p.read_text()) == []

    def test_bundle_with_fake_secret_is_blocked_and_writes_nothing(self, tmp_path):
        # abstract dính secret GIẢ (FAKE) — chuỗi minh họa, không phải credential thật
        doc = Document(
            uid="", source="ieee", source_id="12345678", authority_tier=1, title="Leaky Paper",
            abstract="Config uses IEEE_API_KEY=FAKEsecret1234 for cloud access.",
        )
        db = _seed(tmp_path, doc)
        exports = tmp_path / "exports"
        with pytest.raises(OutboundViolation) as exc:
            build_bundle([doc.uid], db, exports_root=exports, now=FIXED_TS)
        assert "ENV_ASSIGNMENT" in str(exc.value)
        assert "FAKEsecret1234" not in str(exc.value)  # lỗi không lộ lại secret
        # fail-closed: không thư mục bundle nào được ghi ra đĩa
        assert not exports.exists()

    def test_missing_uid_raises_exporter_error(self, tmp_path):
        db = _seed(tmp_path, Document(
            uid="", source="ieee", source_id="12345678", authority_tier=1, title="Present",
        ))
        with pytest.raises(ExporterError):
            build_bundle(["arxiv:9999.99999"], db, exports_root=tmp_path / "exports")

    def test_empty_uid_list_raises(self, tmp_path):
        db = _seed(tmp_path, Document(
            uid="", source="ieee", source_id="12345678", authority_tier=1, title="Present",
        ))
        with pytest.raises(ExporterError):
            build_bundle([], db, exports_root=tmp_path / "exports")
