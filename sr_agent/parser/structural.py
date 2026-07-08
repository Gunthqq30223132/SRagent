"""Structural Parser — bước LLM duy nhất của pipeline, chạy SAU dedup + rubric.

Quy trình cho 1 tài liệu đã qua gate:
  1. Heuristic tách section theo heading (confidence 1.0, không tốn LLM).
  2. LLM evaluator trích TechnicalMetadata (structured output, temperature 0).
  3. LLM sinh đúng 2 câu hỏi phản biện kỹ thuật cho Phần Q&A trang Notion.

Tài liệu chỉ có abstract (chưa tải full-text) vẫn parse được: sections để
trống, evaluator chạy trên abstract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sr_agent.models.schemas import CritiqueQuestion, Document
from sr_agent.parser.evaluator import evaluate_document
from sr_agent.parser.heuristic import build_sections, heuristic_sections
from sr_agent.parser.ollama_client import OllamaClient

_CRITIQUE_SYSTEM_PROMPT = """\
You are a rigorous computer science reviewer. Given a paper's title and
abstract, write EXACTLY TWO deep critical questions that a human reviewer
should answer after reading the full paper.

RULES:
1. Each question must target a specific technical claim, assumption, or
   evaluation choice in the text — no generic questions.
2. Questions must be answerable by reading the paper (not by outside research).
3. Write in English, one sentence each, ending with a question mark.
"""


class _CritiquePair(BaseModel):
    """Schema ép LLM trả đúng 2 câu hỏi."""

    questions: list[str] = Field(min_length=2, max_length=2)


class StructuralParser:
    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()

    def parse(self, doc: Document) -> Document:
        # 1. Heuristic trước — miễn phí, tất định
        roles = heuristic_sections(doc)
        if roles:
            doc.sections = build_sections(doc, roles)

        # 2. Trích siêu dữ liệu kỹ thuật (structured output)
        doc.tech_meta = evaluate_document(doc, self.client)

        # 3. Sinh 2 câu hỏi phản biện cho trang Notion
        pair = self.client.generate_structured(
            system_prompt=_CRITIQUE_SYSTEM_PROMPT,
            user_prompt=f"TITLE: {doc.title}\n\nABSTRACT:\n{doc.abstract or '(none)'}",
            schema_model=_CritiquePair,
        )
        doc.critique_questions = [CritiqueQuestion(question=q) for q in pair.questions]
        return doc
