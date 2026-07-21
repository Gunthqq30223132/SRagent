"""Test Outbound Interceptor integration in NotionPublisher (D39.2)."""

from unittest.mock import MagicMock
import pytest

from sr_agent.models.schemas import DocStatus, Document, RubricResult
from sr_agent.publish.notion_page import NotionPublisher
from sr_agent.store.staging import StagingStore
from tools.guard.outbound import OutboundViolation


def make_clean_doc():
    return Document(
        uid="",
        source="ieee",
        source_id="38111222",
        authority_tier=1,
        title="Clean Paper Title on Machine Learning",
        authors=["Author One"],
        abstract="This paper discusses machine learning algorithms.",
        rubric=RubricResult(total=80, passed=True),
        status=DocStatus.QUEUED,
    )


def make_dirty_doc(secret: str = "sk-proj-abcdef12345678901234567890"):
    doc = make_clean_doc()
    doc.abstract = f"Paper discussing LLM secrets: {secret}"
    return doc, secret


class TestNotionOutboundInterceptor:
    def test_dirty_payload_blocked_live_publish(self, tmp_path):
        with StagingStore(tmp_path / "t.db") as store:
            doc, secret_val = make_dirty_doc()
            store.upsert(doc)
            mock_client = MagicMock()
            publisher = NotionPublisher(
                token="real-token",
                parent_page_id="parent-id",
                client=mock_client,
            )

            with pytest.raises(OutboundViolation) as exc_info:
                publisher.publish(doc, store)

            assert "SECRET_OPENAI_ANTHROPIC" in str(exc_info.value)
            assert secret_val not in str(exc_info.value)

            # Check mock client was never called
            assert mock_client.pages.create.call_count == 0

            # Check doc status remains unchanged (QUEUED)
            stored = store.get(doc.uid)
            assert stored.status is DocStatus.QUEUED
            assert stored.notion_page_id is None

            # Check audit event logged
            events = store.conn.execute("SELECT * FROM events WHERE uid = ?", (doc.uid,)).fetchall()
            assert len(events) == 1
            evt = events[0]
            assert evt["event_type"] == "OUTBOUND_BLOCKED"
            assert "SECRET_OPENAI_ANTHROPIC" in evt["detail"]
            assert secret_val not in evt["detail"]

    def test_clean_payload_publishes_normally(self, tmp_path):
        with StagingStore(tmp_path / "t.db") as store:
            doc = make_clean_doc()
            store.upsert(doc)
            mock_client = MagicMock()
            mock_client.pages.create.return_value = {"id": "page-clean-123"}
            publisher = NotionPublisher(
                token="real-token",
                parent_page_id="parent-id",
                client=mock_client,
            )

            page_id = publisher.publish(doc, store)
            assert page_id == "page-clean-123"
            assert mock_client.pages.create.call_count == 1

            stored = store.get(doc.uid)
            assert stored.status is DocStatus.APPROVED
            assert stored.notion_page_id == "page-clean-123"

            events = store.conn.execute("SELECT * FROM events WHERE uid = ?", (doc.uid,)).fetchall()
            assert len(events) == 1
            assert events[0]["event_type"] == "APPROVED"

    def test_dirty_payload_blocked_dry_run(self, tmp_path):
        with StagingStore(tmp_path / "t.db") as store:
            doc, secret_val = make_dirty_doc(secret="AKIA1234567890ABCDEF")
            store.upsert(doc)
            publisher = NotionPublisher(token="", parent_page_id="")
            assert publisher.dry_run

            with pytest.raises(OutboundViolation) as exc_info:
                publisher.publish(doc, store)

            assert "SECRET_AWS" in str(exc_info.value)
            assert secret_val not in str(exc_info.value)

            stored = store.get(doc.uid)
            assert stored.status is DocStatus.QUEUED

            events = store.conn.execute("SELECT * FROM events WHERE uid = ?", (doc.uid,)).fetchall()
            assert len(events) == 1
            evt = events[0]
            assert evt["event_type"] == "OUTBOUND_BLOCKED"
            assert "SECRET_AWS" in evt["detail"]
            assert secret_val not in evt["detail"]
