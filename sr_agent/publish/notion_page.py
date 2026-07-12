"""Bộ ghi Notion idempotent — chạy khi người dùng bấm Approve trên QC UI.

Trang con chuẩn hóa 3 phần:
  1. Metadata   : đổ toàn bộ metadata Pydantic + tech_meta đã bóc tách.
  2. Q&A        : 2 câu hỏi phản biện dạng toggle, mỗi toggle chứa 3 to_do
                  [CONFIRMED]/[INFERRED]/[UNKNOWN] để người dùng tick.
  3. My Notes   : heading + paragraph trống cho ghi chú cá nhân.

Idempotency: doc đã có notion_page_id -> trả về id cũ, không tạo trang mới.
Dry-run: thiếu NOTION_TOKEN -> in JSON payload ra log/console, status
APPROVED_LOCAL, không crash. Notion API giữ nhịp <=3 req/s nên toàn bộ
blocks gửi trong 1 lệnh pages.create duy nhất (tối đa ~100 blocks — trang
3 phần này dưới 40 blocks, an toàn).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from sr_agent.config import NOTION_PARENT_PAGE_ID, NOTION_TOKEN
from sr_agent.models.schemas import CanonicalRole, DocStatus, Document
from sr_agent.store.staging import StagingStore

logger = logging.getLogger("sr_agent.notion")

QA_LABELS = ("[CONFIRMED]", "[INFERRED]", "[UNKNOWN]")


class TranslationResult(BaseModel):
    translated_text: str


def _rt(text: str) -> list[dict[str, Any]]:
    """rich_text ngắn gọn; Notion giới hạn 2000 ký tự/text object."""
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _heading(text: str) -> dict[str, Any]:
    return {"type": "heading_2", "heading_2": {"rich_text": _rt(text)}}


def _bullet(text: str) -> dict[str, Any]:
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt(text)}}


def _paragraph(text: str = "") -> dict[str, Any]:
    return {"type": "paragraph", "paragraph": {"rich_text": _rt(text) if text else []}}


def build_page_payload(
    doc: Document,
    parent_page_id: str,
    parent_type: str = "page",
    title_prop_name: str = "title",
    vi_abstract: str | None = None
) -> dict[str, Any]:
    """Dựng payload pages.create — pure function, test được không cần API."""
    meta_bullets = [
        _bullet(f"UID: {doc.uid}"),
        _bullet(f"Source: {doc.source} (authority tier {doc.authority_tier})"),
        _bullet(f"Authors: {', '.join(doc.authors) or '—'}"),
        _bullet(f"Published: {doc.published_date.date().isoformat() if doc.published_date else '—'}"),
        _bullet(f"URL: {doc.url or '—'}"),
        _bullet(f"Rubric score: {doc.rubric.total if doc.rubric else '—'}"),
    ]
    if doc.alternate_uids:
        meta_bullets.append(_bullet(f"Merged duplicates: {', '.join(doc.alternate_uids)}"))
    if doc.tech_meta:
        tm = doc.tech_meta
        meta_bullets += [
            _bullet(f"Code repo: {tm.code_repo_url or ('yes' if tm.has_code_repo else 'không thấy')}"),
            _bullet(f"Dataset: {tm.dataset_specification or 'không nêu'}"),
            _bullet(f"Benchmarks: {', '.join(tm.evaluated_benchmarks) or 'không nêu'}"),
            _bullet(f"Declared limitations: {tm.declared_limitations or 'không nêu'}"),
        ]
    # Tóm tắt các phân đoạn đã bóc tách (qua view chuẩn hóa)
    for role, section in doc.canonical_sections.items():
        if section is not None:
            snippet = section.content[:300] + ("…" if len(section.content) > 300 else "")
            meta_bullets.append(_bullet(f"{role.value.title()}: {snippet}"))

    qa_blocks: list[dict[str, Any]] = []
    for i, cq in enumerate(doc.critique_questions[:2], start=1):
        qa_blocks.append({
            "type": "toggle",
            "toggle": {
                "rich_text": _rt(f"Q{i}. {cq.question}"),
                "children": [
                    {"type": "to_do", "to_do": {"rich_text": _rt(label), "checked": False}}
                    for label in QA_LABELS
                ] + [_paragraph("Your answer:")],
            },
        })
    if not qa_blocks:
        qa_blocks.append(_paragraph("(Chưa có câu hỏi phản biện — tài liệu chưa qua LLM parse)"))

    en_paragraphs = [p.strip() for p in doc.abstract.split("\n") if p.strip()] if doc.abstract else ["No abstract available."]
    vi_paragraphs = [p.strip() for p in vi_abstract.split("\n") if p.strip()] if vi_abstract else ["(Chưa dịch được tóm tắt)"]

    en_blocks = [_paragraph(p) for p in en_paragraphs]
    vi_blocks = [_paragraph(p) for p in vi_paragraphs]

    col_list_block = {
        "type": "column_list",
        "column_list": {
            "children": [
                {
                    "type": "column",
                    "column": {
                        "children": [
                            {"type": "heading_3", "heading_3": {"rich_text": _rt("English")}},
                            *en_blocks
                        ]
                    }
                },
                {
                    "type": "column",
                    "column": {
                        "children": [
                            {"type": "heading_3", "heading_3": {"rich_text": _rt("Tiếng Việt")}},
                            *vi_blocks
                        ]
                    }
                }
            ]
        }
    }

    children = [
        _heading("1. Metadata"),
        *meta_bullets,
        col_list_block,
        _heading("2. Q&A — Critical Review"),
        *qa_blocks,
        _heading("3. My Notes"),
        _paragraph(),
    ]
    return {
        "parent": {f"{parent_type}_id": parent_page_id},
        "properties": {
            title_prop_name: {"title": _rt(doc.title)},
        },
        "children": children,
    }


class NotionPublisher:
    def __init__(
        self,
        token: str = NOTION_TOKEN,
        parent_page_id: str = NOTION_PARENT_PAGE_ID,
        client: Any | None = None,  # notion_client.Client hoặc mock trong test
    ):
        self.token = token
        self.parent_page_id = parent_page_id
        self._client = client

    @property
    def dry_run(self) -> bool:
        return not self.token

    @property
    def client(self) -> Any:
        if self._client is None:
            from notion_client import Client  # import trễ: dry-run không cần

            self._client = Client(auth=self.token)
        return self._client

    def publish(self, doc: Document, store: StagingStore) -> str | None:
        """Approve 1 tài liệu. Trả về notion_page_id (None nếu dry-run)."""
        # Idempotent: đã publish rồi thì không tạo trang thứ hai
        stored = store.get(doc.uid)
        if stored and stored.notion_page_id:
            logger.info("%s đã có trang Notion %s — bỏ qua", doc.uid, stored.notion_page_id)
            return stored.notion_page_id

        parent_type = "page"
        title_prop_name = "title"
        if not self.dry_run:
            try:
                db_info = self.client.databases.retrieve(database_id=self.parent_page_id)
                parent_type = "database"
                for k, v in db_info.get("properties", {}).items():
                    if v.get("type") == "title":
                        title_prop_name = k
                        break
            except Exception:
                parent_type = "page"

        vi_abstract = None
        if doc.abstract:
            try:
                from sr_agent.parser.ollama_client import OllamaClient
                client = OllamaClient()
                if client.is_available():
                    system_prompt = (
                        "You are a professional academic translator. Your task is to translate the "
                        "provided academic paper abstract into natural, professional Vietnamese. "
                        "Keep technical terms accurate."
                    )
                    user_prompt = f"Abstract to translate:\n{doc.abstract}"
                    res = client.generate_structured(system_prompt, user_prompt, TranslationResult)
                    vi_abstract = res.translated_text
            except Exception as e:
                logger.warning("Không thể dịch tự động abstract qua Ollama: %s", e)

        payload = build_page_payload(
            doc,
            self.parent_page_id or "<parent-page-id>",
            parent_type=parent_type,
            title_prop_name=title_prop_name,
            vi_abstract=vi_abstract
        )

        if self.dry_run:
            logger.warning("NOTION_TOKEN trống — DRY-RUN, in payload thay vì gọi API")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            doc.status = DocStatus.APPROVED_LOCAL
            store.upsert(doc)
            store.log_event(doc.uid, "APPROVED", "dry-run (không có NOTION_TOKEN)")
            return None

        page = self.client.pages.create(**payload)
        doc.notion_page_id = page["id"]
        doc.status = DocStatus.APPROVED
        store.upsert(doc)
        store.log_event(doc.uid, "APPROVED", f"notion page {page['id']}")
        return page["id"]
