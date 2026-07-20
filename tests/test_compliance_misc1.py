import json
import os
import re
import subprocess
from pathlib import Path
import pytest
import respx
import httpx
from pydantic import ValidationError

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.protocol_build import ReviewProtocol, ExtractionField, PicoConcept
from tools.evidence_extract import run_extraction_batch, LEGACY_EXTRACTION_FIELDS
from sr_agent.parser.ollama_client import OllamaClient
from sr_agent.doctor import check_model_digests, check_model_drift

OLLAMA = "http://localhost:11434"

@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


class TestDynamicSchema:
    def test_valid_protocol_extraction_fields(self):
        proto = ReviewProtocol(
            topic_vi="test",
            population=PicoConcept(concept="A"),
            intervention=PicoConcept(concept="B"),
            exclusion_criteria=[],
            extraction_fields=[
                ExtractionField(id="dose_val", description_en="Dose of drug"),
                ExtractionField(id="primary_outcome", description_en="Primary outcome", value_hint="int")
            ]
        )
        assert len(proto.extraction_fields) == 2

    def test_invalid_field_id_pattern(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewProtocol(
                topic_vi="test",
                population=PicoConcept(concept="A"),
                intervention=PicoConcept(concept="B"),
                exclusion_criteria=[],
                extraction_fields=[
                    ExtractionField(id="Dose-Val", description_en="starts with capital and hyphen")
                ]
            )
        assert "Invalid extraction field ID" in str(exc_info.value)

    def test_duplicate_field_ids_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewProtocol(
                topic_vi="test",
                population=PicoConcept(concept="A"),
                intervention=PicoConcept(concept="B"),
                exclusion_criteria=[],
                extraction_fields=[
                    ExtractionField(id="dose_val", description_en="First"),
                    ExtractionField(id="dose_val", description_en="Second")
                ]
            )
        assert "Duplicate extraction field ID" in str(exc_info.value)

    @respx.mock
    def test_dynamic_extraction_execution(self, store):
        doc = Document(
            uid="arxiv:1234.5678", source="arxiv", source_id="arxiv:1234.5678", authority_tier=1,
            title="A title", abstract="We used 50 mg of Sevoflurane."
        )
        doc.status = DocStatus.QUEUED
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")

        proto = ReviewProtocol(
            topic_vi="inhaled anesthetics",
            population=PicoConcept(concept="anesthetics"),
            intervention=PicoConcept(concept="sevoflurane"),
            exclusion_criteria=[],
            extraction_fields=[
                ExtractionField(id="anesthetic_dose", description_en="The dose of the volatile agent", value_hint="mg")
            ]
        )

        dummy_response = {
            "anesthetic_dose": {"value": "50 mg", "quote": "50 mg of Sevoflurane", "section": "abstract"}
        }

        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_response)}
        }))

        count = run_extraction_batch(store, limit=1, protocol=proto)
        assert count == 1

        exts = store.extractions(doc.uid, verified_only=False)
        assert len(exts) == 1
        assert exts[0]["field"] == "anesthetic_dose"
        assert exts[0]["value"] == "50 mg"
        assert exts[0]["verified"] == 1


class TestModelDigestsPinning:
    @respx.mock
    def test_digest_match_ok(self):
        client = OllamaClient(base_url=OLLAMA)
        mock_tags = {
            "models": [
                {"name": "llama3.1:8b", "digest": "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"},
                {"name": "gemma4:e4b", "digest": "sha256:c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"},
                {"name": "qwen2.5:7b-instruct", "digest": "sha256:845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"}
            ]
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json=mock_tags))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={}))

        res = check_model_digests(client)
        assert res.ok is True
        assert "tất cả model khớp" in res.detail

    @respx.mock
    def test_digest_mismatch_warning(self, store):
        client = OllamaClient(base_url=OLLAMA)
        mock_tags = {
            "models": [
                {"name": "llama3.1:8b", "digest": "sha256:mismatchedhash1234567890abcdef1234567890abcdef1234567890abcdef"},
                {"name": "gemma4:e4b", "digest": "sha256:c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"},
                {"name": "qwen2.5:7b-instruct", "digest": "sha256:845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"}
            ]
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json=mock_tags))
        res = check_model_digests(client)
        assert res.ok is False
        assert "lệch digest" in res.detail

        check_model_drift(store, "screening:batch", client)
        events = [r["event_type"] for r in store.conn.execute("SELECT event_type FROM events WHERE uid = 'screening:batch'").fetchall()]
        assert "MODEL_DRIFT" in events


class TestBackupStaging:
    def test_backup_and_rotation(self, tmp_path):
        db_path = tmp_path / "staging.db"
        with StagingStore(db_path) as s:
            s.conn.execute("CREATE TABLE foo (bar TEXT)")
            s.conn.execute("INSERT INTO foo VALUES ('hello')")
            s.conn.commit()

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        dummy_files = []
        for i in range(1, 10):
            dummy_file = backup_dir / f"staging-20260720-00000{i}.db"
            dummy_file.write_text("dummy database content")
            dummy_files.append(dummy_file)

        script_path = Path(__file__).resolve().parent.parent / "scripts" / "backup_staging.sh"
        subprocess.run(["bash", str(script_path), str(db_path)], check=True)

        remaining_files = sorted(backup_dir.glob("staging-*.db"))
        assert len(remaining_files) == 7

        assert "000001" not in remaining_files[0].name
        assert "000002" not in remaining_files[0].name
        assert "000003" not in remaining_files[0].name

        newest_file = remaining_files[-1]
        with StagingStore(newest_file) as s:
            res = s.conn.execute("SELECT bar FROM foo").fetchone()
            assert res["bar"] == "hello"
