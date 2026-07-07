"""Tests cho tools/topic_run.py — cầu nối ngữ nghĩa → ID. Offline 100%."""

import json

import httpx
import pytest
import respx

from sr_agent.models.schemas import DocStatus
from sr_agent.store.staging import StagingStore
from tests.test_pipeline import FakeFetcher, make_doc
from tools.topic_run import (
    DEFAULT_PROFILE,
    ProfiledFetcher,
    _validate_id,
    expand_terms,
    ingest_manifest,
    load_profile,
    plan,
    render_queries,
    run_direct,
)

OLLAMA = "http://localhost:11434"


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


class TestProfile:
    def test_default_profile_loads_and_renders(self):
        profile = load_profile(DEFAULT_PROFILE)
        qs = render_queries(profile, "arxiv", ["retrieval augmented generation"])
        assert qs == ['"retrieval augmented generation"']

    def test_multi_terms_multi_templates_union_dedup(self):
        profile = {"sources": {"ieee": {"templates": ['"{terms}"', '{terms} survey']}}}
        qs = render_queries(profile, "ieee", ["rag", "rag"])  # terms trùng
        assert qs == ['"rag"', "rag survey"]

    def test_unknown_source_renders_empty(self):
        assert render_queries({"sources": {}}, "arxiv", ["x"]) == []


class TestProfiledFetcher:
    def test_ignores_passed_query_and_unions_profile_queries(self):
        calls = []

        class Spy:
            source = "ieee"

            def search(self, query, max_results=20):
                calls.append(query)
                return {"q1": ["11111111", "22222222"],
                        "q2": ["22222222", "33333333"]}[query]

            def fetch(self, ids):
                return ids

        wrapped = ProfiledFetcher(Spy(), queries=["q1", "q2"])
        ids = wrapped.search("QUERY GOC BI BO QUA", max_results=20)
        assert calls == ["q1", "q2"]  # query gốc không bao giờ chạm adapter
        assert ids == ["11111111", "22222222", "33333333"]  # union giữ thứ tự

    def test_caps_at_max_results(self):
        class Many:
            source = "ieee"

            def search(self, query, max_results=20):
                return [f"1000000{i}" for i in range(10)]

            def fetch(self, ids):
                return ids

        assert len(ProfiledFetcher(Many(), ["q"]).search("x", max_results=3)) == 3


class TestValidateId:
    def test_arxiv_normalized(self):
        assert _validate_id("arxiv", "2401.12345v2") == "arxiv:2401.12345"

    def test_ieee_exact_regex(self):
        assert _validate_id("ieee", "38111222") == "38111222"
        assert _validate_id("ieee", "123") is None
        assert _validate_id("ieee", "38111222; DROP TABLE") is None


class TestPlanMode:
    def test_manifest_has_items_provenance_and_rejects(self):
        class MixedFetcher:
            source = "ieee"

            def search(self, query, max_results=20):
                return ["38111222", "not-an-id"]

            def fetch(self, ids):
                return []

        manifest = plan("chủ đề gốc tiếng Việt", {"ieee": ["q1"]},
                        {"ieee": MixedFetcher()}, max_per_source=20)
        assert manifest["topic"] == "chủ đề gốc tiếng Việt"
        assert manifest["items"] == [
            {"source": "ieee", "id": "38111222", "rank": 1, "found_by_query": "q1"}
        ]
        assert manifest["rejected"][0]["raw_id"] == "not-an-id"

    def test_plan_never_touches_fetch(self):
        class NoFetch:
            source = "arxiv"

            def search(self, query, max_results=20):
                return ["arxiv:2401.12345"]

            def fetch(self, ids):
                raise AssertionError("plan không được fetch nội dung")

        manifest = plan("t", {"arxiv": ["q"]}, {"arxiv": NoFetch()}, 5)
        assert len(manifest["items"]) == 1


class TestIngestManifest:
    def test_valid_ids_flow_through_real_pipeline(self, store):
        doc = make_doc("ieee", "38111222", "Bridge Paper", 1)
        manifest = {"items": [{"source": "ieee", "id": "38111222"}]}
        report = ingest_manifest(store, manifest,
                                 {"ieee": FakeFetcher("ieee", [doc])})
        assert report.queued == 1
        assert store.get("ieee:38111222").status is DocStatus.QUEUED

    def test_hand_edited_bad_id_is_dropped_at_boundary(self, store):
        manifest = {"items": [{"source": "ieee", "id": "khong-phai-id"}]}
        report = ingest_manifest(store, manifest,
                                 {"ieee": FakeFetcher("ieee", [])})
        assert report.fetched == 0 and report.queued == 0  # biên tự vệ


class TestRunDirect:
    def test_profiled_run_records_heartbeat(self, store):
        doc = make_doc("arxiv", "arxiv:2401.12345", "Direct Paper", 2)
        report = run_direct(
            store, "chủ đề nhãn", {"arxiv": ["q-profile"]},
            {"arxiv": FakeFetcher("arxiv", [doc])},
        )
        assert report.queued == 1
        run = store.last_run()  # M4 heartbeat phải được ghi như CLI thật
        assert run["query"] == "chủ đề nhãn"


class TestExpand:
    @respx.mock
    def test_expand_merges_llm_terms(self):
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant",
                        "content": json.dumps({"terms": ["agent harness", "rag"]})}
        }))
        merged = expand_terms("chủ đề", ["rag"])
        assert merged == ["rag", "agent harness"]  # dedupe, giữ terms gốc trước

    @respx.mock
    def test_expand_falls_back_when_ollama_down(self):
        respx.get(f"{OLLAMA}/api/tags").mock(side_effect=httpx.ConnectError("down"))
        assert expand_terms("chủ đề", ["rag"]) == ["rag"]  # suy giảm êm
