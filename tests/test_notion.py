import json
from unittest.mock import MagicMock

from sr_agent.models.schemas import (
    CritiqueQuestion,
    DocStatus,
    Document,
    RubricResult,
    TechnicalMetadata,
)
from sr_agent.publish.notion_page import QA_LABELS, NotionPublisher, build_page_payload
from sr_agent.store.staging import StagingStore


def make_doc():
    return Document(
        uid="", source="ieee", source_id="38111222", authority_tier=1,
        title="Efficient Transformer Inference",
        authors=["Alice Nguyen"],
        rubric=RubricResult(total=88, passed=True),
        tech_meta=TechnicalMetadata(
            has_code_repo=True, code_repo_url="https://github.com/x",
            evaluated_benchmarks=["GLUE"],
        ),
        critique_questions=[
            CritiqueQuestion(question="Why encoder-only?"),
            CritiqueQuestion(question="How was speedup measured?"),
        ],
        status=DocStatus.QUEUED,
    )


class TestPayload:
    def test_three_part_structure(self):
        payload = build_page_payload(make_doc(), "parent123")
        assert payload["parent"] == {"page_id": "parent123"}
        headings = [
            b["heading_2"]["rich_text"][0]["text"]["content"]
            for b in payload["children"] if b["type"] == "heading_2"
        ]
        assert headings == ["1. Metadata", "2. Q&A — Critical Review", "3. My Notes"]
        # Phần 3 kết thúc bằng paragraph trống cho ghi chú cá nhân
        assert payload["children"][-1] == {"type": "paragraph", "paragraph": {"rich_text": []}}

    def test_qa_toggles_have_three_static_labels(self):
        payload = build_page_payload(make_doc(), "p")
        toggles = [b for b in payload["children"] if b["type"] == "toggle"]
        assert len(toggles) == 2
        for toggle in toggles:
            todos = [c for c in toggle["toggle"]["children"] if c["type"] == "to_do"]
            labels = [t["to_do"]["rich_text"][0]["text"]["content"] for t in todos]
            assert labels == list(QA_LABELS)
            assert all(t["to_do"]["checked"] is False for t in todos)

    def test_payload_is_json_serializable(self):
        json.dumps(build_page_payload(make_doc(), "p"))


class TestDryRun:
    def test_missing_token_prints_payload_and_sets_local_status(self, tmp_path, capsys):
        with StagingStore(tmp_path / "t.db") as store:
            doc = make_doc()
            store.upsert(doc)
            publisher = NotionPublisher(token="", parent_page_id="")
            assert publisher.dry_run

            page_id = publisher.publish(doc, store)
            assert page_id is None
            printed = json.loads(capsys.readouterr().out)
            assert printed["children"][0]["type"] == "heading_2"
            assert store.get(doc.uid).status is DocStatus.APPROVED_LOCAL

    def test_approved_local_exempt_from_ttl_purge(self, tmp_path):
        from datetime import datetime, timedelta, timezone

        with StagingStore(tmp_path / "t.db") as store:
            doc = make_doc()
            doc.status = DocStatus.APPROVED_LOCAL
            store.upsert(doc)
            old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
            store.conn.execute("UPDATE documents SET last_interaction_at = ?", (old,))
            store.conn.commit()
            assert store.purge_expired(ttl_hours=72) == []


class TestRealPublish:
    def test_creates_page_and_stores_id(self, tmp_path):
        with StagingStore(tmp_path / "t.db") as store:
            doc = make_doc()
            store.upsert(doc)
            mock_client = MagicMock()
            mock_client.pages.create.return_value = {"id": "page-abc"}
            publisher = NotionPublisher(token="secret", parent_page_id="parent123",
                                        client=mock_client)

            assert publisher.publish(doc, store) == "page-abc"
            stored = store.get(doc.uid)
            assert stored.status is DocStatus.APPROVED
            assert stored.notion_page_id == "page-abc"

    def test_idempotent_second_approve_no_duplicate_page(self, tmp_path):
        with StagingStore(tmp_path / "t.db") as store:
            doc = make_doc()
            store.upsert(doc)
            mock_client = MagicMock()
            mock_client.pages.create.return_value = {"id": "page-abc"}
            publisher = NotionPublisher(token="secret", parent_page_id="p",
                                        client=mock_client)

            publisher.publish(doc, store)
            again = publisher.publish(store.get(doc.uid), store)
            assert again == "page-abc"
            assert mock_client.pages.create.call_count == 1  # không tạo trang thứ 2
