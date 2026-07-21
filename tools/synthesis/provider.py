"""SynthesisProvider — adapter Layer C với fallback BẤT ĐỐI XỨNG (D31 §3).

Hợp đồng đóng cứng tại docs/specs/D31-orchestration-cloud-hybrid.md §3. Điểm bất biến:

- fail-closed: mọi đầu ra provider PHẢI qua Numeric Firewall V24 (§4) trước khi trả;
  một anchor số bịa ⇒ verdict void (passed=False) — KHÔNG "sửa cho khớp" văn bản.
- temp 0 + structured: gọi Ollama qua `generate_structured` (constrained decoding).
- CẤM cosine/fuzzy trong verify: chỉ dựa vào firewall (substring byte-exact).
- fallback BẤT ĐỐI XỨNG:
    cloud → local : TỰ ĐỘNG (suy giảm riêng tư hóa, an toàn). In cảnh báo 1 dòng.
    local → cloud : KHÔNG BAO GIỜ TỰ ĐỘNG. Ollama sập không phải lý do xuất dữ liệu
                    ra ngoài; cloud chỉ chạy khi có cờ tường minh --allow-cloud
                    (hoặc env SR_ALLOW_CLOUD=1) và payload đã qua assert_sanitized() (§5).

Module ngoài core (`tools/`), CHỈ IMPORT `tools/guard/` — không sửa một dòng guard nào.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # chạy được khi chưa pip install -e

from pydantic import BaseModel, Field, ValidationError

from sr_agent.config import OLLAMA_MODEL
from sr_agent.errors import SchemaValidationError
from sr_agent.parser.ollama_client import OllamaClient
from tools.guard.firewall import FirewallVerdict, check_output
from tools.guard.outbound import assert_sanitized

logger = logging.getLogger("tools.synthesis.provider")

DEFAULT_PROVIDER = "ollama"


# --- Hợp đồng dữ liệu (§3) ----------------------------------------------------


class SourceDoc(BaseModel):
    """Một nguồn Layer A đưa vào tầng tổng hợp — markdown là CANONICAL, không chèn anchor."""

    uid: str                 # ieee:… | arxiv:… — nối về staging store
    markdown: str            # Docling output, canonical, không chèn anchor inline
    source_map_entry: str = ""  # 1 dòng mô tả trong Source Map


class SynthesisResult(BaseModel):
    """Kết quả tổng hợp LUÔN đính kèm verdict firewall — không verdict = không kết quả."""

    text: str
    citations: list[str]         # uid các nguồn được viện dẫn — BẮT BUỘC khác rỗng để hợp lệ
    provider: str
    firewall: FirewallVerdict    # verdict tất định — void ⇔ passed=False

    @property
    def is_valid(self) -> bool:
        """Hợp lệ ⇔ firewall thông qua VÀ có ít nhất một citation."""
        return self.firewall.passed and bool(self.citations)


@runtime_checkable
class SynthesisProvider(Protocol):
    name: str
    is_local: bool

    def is_available(self) -> bool: ...

    def synthesize(
        self,
        question: str,
        sources: list[SourceDoc],
        schema_model: type[BaseModel] | None = None,
    ) -> SynthesisResult: ...


# --- Lỗi phân tầng ------------------------------------------------------------


class SynthesisError(Exception):
    """Gốc của lỗi tầng tổng hợp."""


class SynthesisConfigError(SynthesisError):
    """Cấu hình sai: provider không rõ, hoặc tính năng chưa hiện thực."""


class CloudNotAllowedError(SynthesisConfigError):
    """Chặn cloud chạy tự động — vi phạm chính sách bất đối xứng D31 §3."""

    def __init__(self, name: str):
        super().__init__(
            f"Provider '{name}' là CLOUD và bị chặn tự động (chính sách bất đối xứng "
            f"D31 §3): local→cloud KHÔNG BAO GIỜ tự động. Ollama sập không phải lý do "
            f"xuất dữ liệu ra ngoài. Chỉ chạy cloud khi có cờ tường minh --allow-cloud "
            f"(hoặc env SR_ALLOW_CLOUD=1), và payload đã qua assert_sanitized()."
        )


class ProviderUnavailable(SynthesisError):
    """Provider không phản hồi (Ollama sập / cloud hết quota)."""


class SynthesisInputError(SynthesisError):
    """Input không hợp lệ (thiếu nguồn)."""


# --- Envelope structured cho Ollama -------------------------------------------


class _SynthesisDraft(BaseModel):
    """Khung JSON Ollama phải điền — tách bạch answer và citations (temp 0, schema)."""

    answer: str = Field(
        description="The synthesized answer, grounded ONLY in the provided sources."
    )
    citations: list[str] = Field(
        default_factory=list,
        description="uid of every source document actually cited; must be non-empty.",
    )


_SYNTH_SYSTEM_PROMPT = (
    "You are a synthesis assistant inside a systematic-review pipeline.\n"
    "Rules you MUST obey:\n"
    "- Answer the QUESTION using ONLY the numbered SOURCES provided.\n"
    "- Never invent numbers, ports, versions, percentages, units, or complexity "
    "classes. Every technical constant you state must appear verbatim in a source.\n"
    "- Put the uid of every source you actually rely on into `citations` "
    "(never empty).\n"
    "- If the sources do not contain the answer, say so plainly and still cite the "
    "closest source(s).\n"
    "Return JSON matching the schema exactly."
)


def _build_user_prompt(question: str, sources: list[SourceDoc]) -> str:
    blocks = "\n\n".join(f"[{s.uid}]\n{s.markdown}" for s in sources)
    return f"QUESTION:\n{question}\n\nSOURCES:\n{blocks}"


def _finalize(
    text: str,
    citations: list[str],
    sources: list[SourceDoc],
    *,
    provider: str,
    schema_model: type[BaseModel] | None = None,
) -> SynthesisResult:
    """Chốt tất định chung cho MỌI provider: firewall trước, không mutate văn bản.

    Học thuyết: "LLM đề xuất, verifier tất định định đoạt". Con số bịa ⇒ verdict
    void; văn bản gốc giữ nguyên (không sửa cho khớp — đó sẽ là ngụy tạo bằng chứng).
    """
    verdict = check_output(text, [s.markdown for s in sources], strict=True)
    if schema_model is not None and verdict.passed:
        # Cổng kiểm định bổ sung (tùy chọn): answer phải khớp schema của caller.
        try:
            schema_model.model_validate_json(text)
        except ValidationError as exc:
            raise SchemaValidationError(
                f"answer không qua được schema {schema_model.__name__}: {exc}"
            ) from exc
    return SynthesisResult(
        text=text,
        citations=list(citations),
        provider=provider,
        firewall=verdict,
    )


# --- OllamaSynthesisProvider (mặc định, local) --------------------------------


class OllamaSynthesisProvider:
    """Provider mặc định: bọc OllamaClient.generate_structured (temp 0, schema).

    Model lấy từ env SR_SYNTH_MODEL (fallback OLLAMA_MODEL) — KHÔNG hard-code tên
    model (bài học gemma3:4b→gemma4:e4b của M6-hotfix). Ollama vắng/chết → báo ồn
    ào (ProviderUnavailable), KHÔNG âm thầm nhảy sang cloud.
    """

    name = "ollama"
    is_local = True

    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str | None = None,
    ):
        self._model = model or os.getenv("SR_SYNTH_MODEL") or OLLAMA_MODEL
        self._client = client or OllamaClient(model=self._model)

    def is_available(self) -> bool:
        return self._client.is_available()

    def synthesize(
        self,
        question: str,
        sources: list[SourceDoc],
        schema_model: type[BaseModel] | None = None,
    ) -> SynthesisResult:
        if not sources:
            raise SynthesisInputError("synthesize cần ít nhất một SourceDoc.")
        if not self.is_available():
            raise ProviderUnavailable(
                f"Ollama không phản hồi tại {self._client.base_url}. Đây KHÔNG phải "
                f"lý do tự chuyển sang cloud (chính sách bất đối xứng D31 §3): khởi "
                f"động Ollama rồi chạy lại, hoặc bật cloud tường minh bằng --allow-cloud."
            )
        draft = self._client.generate_structured(
            system_prompt=_SYNTH_SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(question, sources),
            schema_model=_SynthesisDraft,
        )
        return _finalize(
            draft.answer,
            draft.citations,
            sources,
            provider=self.name,
            schema_model=schema_model,
        )


# Bí danh theo tên trong bảng §3 (OllamaProvider) — cùng một lớp.
OllamaProvider = OllamaSynthesisProvider


# --- Placeholder cloud (D31.3) — giữ đường outbound guard sống & test được ------


class _GeminiPlaceholderProvider:
    """Chỗ đặt GeminiFileSearchProvider (D31.3). CHƯA hiện thực kênh cloud.

    Dù chưa gửi được, mọi payload rời máy vẫn phải qua assert_sanitized (§5) — chốt
    chặn outbound là bất biến của ĐƯỜNG cloud, không đợi tính năng hoàn chỉnh.
    """

    name = "gemini"
    is_local = False

    def is_available(self) -> bool:
        return False

    def synthesize(
        self,
        question: str,
        sources: list[SourceDoc],
        schema_model: type[BaseModel] | None = None,
    ) -> SynthesisResult:
        # Chốt chặn CUỐI trước socket: mọi byte rời máy phải sạch (§5).
        for src in sources:
            assert_sanitized(src.markdown)
        assert_sanitized(question)
        raise SynthesisConfigError(
            "GeminiFileSearchProvider thuộc D31.3 — chưa hiện thực kênh cloud. "
            "Payload đã qua assert_sanitized nhưng chưa có đích để gửi."
        )


# --- Registry & policy router (chép nguyên tắc §3) ----------------------------


@dataclass(frozen=True)
class _ProviderSpec:
    is_local: bool
    factory: Callable[..., SynthesisProvider]


def _make_ollama(*, client: OllamaClient | None = None) -> SynthesisProvider:
    return OllamaSynthesisProvider(client=client)


def _make_gemini(*, client: OllamaClient | None = None) -> SynthesisProvider:
    return _GeminiPlaceholderProvider()


_REGISTRY: dict[str, _ProviderSpec] = {
    "ollama": _ProviderSpec(is_local=True, factory=_make_ollama),
    # Cloud đăng ký với is_local=False → router đòi allow_cloud tường minh (D31.3).
    "gemini": _ProviderSpec(is_local=False, factory=_make_gemini),
}


def _cloud_opt_in(allow_cloud: bool) -> bool:
    """Opt-in cloud = cờ --allow-cloud HOẶC env SR_ALLOW_CLOUD=1 (đều tường minh)."""
    return bool(allow_cloud) or os.getenv("SR_ALLOW_CLOUD", "").strip() == "1"


def resolve_provider_name(name: str | None = None) -> str:
    return (name or os.getenv("SR_SYNTH_PROVIDER") or DEFAULT_PROVIDER).strip().lower()


def get_provider(
    name: str | None = None,
    *,
    allow_cloud: bool = False,
    client: OllamaClient | None = None,
) -> SynthesisProvider:
    """Chọn provider theo tên/env. Cloud bị chặn trừ khi opt-in tường minh.

    Bất biến: registry KHÔNG BAO GIỜ trả provider cloud khi thiếu --allow-cloud
    (hoặc env SR_ALLOW_CLOUD=1) — vi phạm = âm thầm xuất dữ liệu, cấm từ M1.
    """
    name = resolve_provider_name(name)
    spec = _REGISTRY.get(name)
    if spec is None:
        raise SynthesisConfigError(
            f"Provider tổng hợp không rõ: {name!r}. Hợp lệ: {sorted(_REGISTRY)}."
        )
    if not spec.is_local and not _cloud_opt_in(allow_cloud):
        raise CloudNotAllowedError(name)
    return spec.factory(client=client)


def synthesize(
    question: str,
    sources: list[SourceDoc],
    *,
    provider: str | None = None,
    allow_cloud: bool = False,
    client: OllamaClient | None = None,
) -> SynthesisResult:
    """Tổng hợp qua provider đã chọn, áp dụng fallback BẤT ĐỐI XỨNG (§3).

    - cloud → local: cloud không khả dụng/hết quota ⇒ TỰ ĐỘNG lui về Ollama local,
      in cảnh báo 1 dòng (chỉ mất độ rộng suy luận, không mất an toàn).
    - local → cloud: local sập ⇒ RAISE, KHÔNG bao giờ tự nhảy sang cloud.
    """
    prov = get_provider(provider, allow_cloud=allow_cloud, client=client)
    try:
        return prov.synthesize(question, sources)
    except ProviderUnavailable:
        if prov.is_local:
            raise  # local → cloud KHÔNG BAO GIỜ tự động
        logger.warning(
            "Cloud provider %r không khả dụng → tự động lui về Ollama local "
            "(suy giảm riêng tư hóa, an toàn).",
            prov.name,
        )
        return get_provider("ollama", client=client).synthesize(question, sources)
