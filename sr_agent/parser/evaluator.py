"""Structural CS Quality Analyzer — bóc tách siêu dữ liệu kỹ thuật khách quan.

LLM chỉ được phép TRÍCH thông tin nêu tường minh trong Abstract/Introduction;
cấm suy diễn. Kết quả ép khớp 100% TechnicalMetadata qua Ollama structured
output. Trường nào không tìm thấy bằng chứng trực tiếp -> null/false/[].
"""

from __future__ import annotations

from sr_agent.models.schemas import CanonicalRole, Document, TechnicalMetadata
from sr_agent.parser.ollama_client import OllamaClient

CS_ANALYZER_SYSTEM_PROMPT = """\
You are a Structural CS Quality Analyzer for computer science papers.
You extract ONLY technical facts that are stated verbatim in the provided text.

STRICT RULES:
1. Extraction only — NEVER infer, guess, or use outside knowledge.
2. If the text does not explicitly state a fact, return null (or false, or []).
3. has_code_repo is true ONLY if an explicit repository link or an explicit
   statement like "code is available at ..." appears in the text.
4. code_repo_url must be copied character-for-character from the text; null if absent.
5. dataset_specification: quote the dataset size or name exactly as written
   (e.g. "10,000 samples", "ImageNet-1k"); null if no dataset is mentioned.
6. evaluated_benchmarks: list standard benchmark names explicitly used for
   comparison (e.g. GLUE, SQuAD, MMLU, ImageNet); [] if none are named.
7. declared_limitations: summarize ONLY limitations the authors themselves
   acknowledge (phrases like "we acknowledge", "our approach is limited to",
   "does not handle"); null if the authors declare none.
8. Output must match the JSON schema exactly. No commentary.
"""

_USER_TEMPLATE = """\
Extract the technical metadata from this paper's abstract/introduction.

TITLE: {title}

TEXT:
{text}
"""


def evaluate_document(doc: Document, client: OllamaClient | None = None) -> TechnicalMetadata:
    """Chấm siêu dữ liệu kỹ thuật cho 1 tài liệu từ Abstract/Introduction."""
    client = client or OllamaClient()
    context = doc.abstract or ""
    # Ghép Abstract + phân đoạn CONTEXT (Introduction/Problem) qua view chuẩn hóa
    ctx_sec = doc.canonical_sections[CanonicalRole.CONTEXT]
    if ctx_sec is not None:
        context = f"{context}\n\n{ctx_sec.content}".strip()
    if not context:
        # Không có gì để trích: trả metadata rỗng tất định, không tốn LLM
        return TechnicalMetadata(has_code_repo=False)

    return client.generate_structured(
        system_prompt=CS_ANALYZER_SYSTEM_PROMPT,
        user_prompt=_USER_TEMPLATE.format(title=doc.title, text=context[:8000]),
        schema_model=TechnicalMetadata,
    )
