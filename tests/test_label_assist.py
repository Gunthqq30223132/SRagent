"""Test cho trợ lý dán nhãn vàng M7.2-MED."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools import label_assist as la
from tools.protocol_build import PicoConcept, ReviewProtocol

ABSTRACT = (
    "Postoperative cognitive dysfunction remains a concern. "
    "Patients were randomly assigned to sevoflurane (n=60) or propofol (n=58). "
    "The primary outcome was POCD incidence at day 7. "
    "We administered 50 mg of the study drug. "
    "Funding was provided by an institutional grant."
)


@pytest.fixture
def protocol():
    return ReviewProtocol(
        topic_vi="gây mê",
        population=PicoConcept(concept="surgical patients"),
        intervention=PicoConcept(concept="sevoflurane", synonyms=["volatile"]),
        comparison=PicoConcept(concept="propofol"),
        outcome=PicoConcept(concept="POCD"),
        exclusion_criteria=["ET1", "ET3"],
        unit_lexicon=["mg", "min"],
    )


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


# --- Bất biến nền: đường dán nhãn KHÔNG được chạm LLM ---------------------------------


def test_label_path_never_touches_an_llm():
    """Đối kháng: nếu ai đó nối LLM vào đường dán nhãn, nhãn vàng thành vòng lặp
    tự chứng và toàn bộ phép hiệu chuẩn mất ý nghĩa. Khóa ở mức source code."""
    src = Path(la.__file__).read_text(encoding="utf-8")
    for forbidden in ("OllamaClient", "generate_structured", "ollama"):
        assert forbidden not in src, f"{forbidden} xuất hiện trong đường dán nhãn"


def test_rendered_item_contains_no_verdict_suggestion(protocol):
    """Máy đưa bằng chứng, KHÔNG đưa phán quyết — màn hình không được gợi ý."""
    item = {"pmid": "1", "title": "T", "abstract": ABSTRACT, "is_decoy": "0"}
    rendered = la._render_item(item, protocol, color=False, full=False)
    for leak in ("INCLUDE", "EXCLUDE", "nên nhận", "nên loại", "gợi ý"):
        assert leak not in rendered


# --- Chọn bằng chứng tất định ---------------------------------------------------------


def test_evidence_is_verbatim_substring_of_abstract(protocol):
    """Không diễn giải, không tóm tắt ⇒ không có đường nào để bịa."""
    for sent in la.select_evidence(ABSTRACT, protocol):
        assert sent in ABSTRACT


def test_evidence_prefers_dose_and_design_over_boilerplate(protocol):
    evidence = la.select_evidence(ABSTRACT, protocol, k=3)
    joined = " ".join(evidence)
    assert "50 mg" in joined            # liều — số kèm đơn vị
    assert "randomly assigned" in joined  # thiết kế nghiên cứu
    assert "Funding was provided" not in joined  # boilerplate bị loại


def test_evidence_keeps_original_order(protocol):
    evidence = la.select_evidence(ABSTRACT, protocol, k=3)
    positions = [ABSTRACT.index(s) for s in evidence]
    assert positions == sorted(positions)


def test_dose_sentence_is_always_surfaced_even_if_outranked(protocol):
    """Câu mang liều phải luôn hiện, kể cả khi thua điểm câu nhiều từ PICO.

    Với SR lâm sàng, liều/tỉ lệ kết cục là loại thông tin khác hẳn về bản chất —
    bỏ sót nó là bỏ sót đúng thứ bác sĩ cần để phán.
    """
    abstract = (
        "Sevoflurane and propofol in surgical patients with POCD are widely studied. "
        "Sevoflurane versus propofol in surgical patients remains debated for POCD. "
        "Sevoflurane and propofol comparisons in surgical patients address POCD. "
        "Depth was held at 1.0 mg throughout."
    )
    evidence = la.select_evidence(abstract, protocol, k=3)
    assert any("1.0 mg" in s for s in evidence)


def test_number_with_unit_outscores_bare_number(protocol):
    groups = la.collect_terms(protocol)
    with_unit = la.score_sentence("Dose was 50 mg total.", groups, ["mg"])
    bare = la.score_sentence("There were 50 total.", groups, ["mg"])
    assert with_unit > bare


def test_matching_is_substring_exact_not_fuzzy(protocol):
    groups = la.collect_terms(protocol)
    # 'sevoflurane' là substring ⇒ tính điểm.
    assert la.score_sentence("Sevoflurane was used.", groups, []) > 0
    # 'sevofluranx' KHÔNG phải substring ⇒ không tính (không có fuzzy, bất biến #2).
    # Cố ý tránh chữ số trong ví dụ: luật số chấm điểm độc lập với luật từ khóa.
    assert la.score_sentence("Sevofluranx was used.", groups, []) == 0


def test_empty_abstract_returns_no_evidence(protocol):
    assert la.select_evidence("", protocol) == []


# --- Đọc/ghi + khả năng chạy tiếp ----------------------------------------------------


def test_gold_file_is_resumable(tmp_path):
    gold = tmp_path / "gold.csv"
    la.append_gold(gold, {
        "pmid": "111", "uid": "europepmc:MED:111", "is_decoy": "0",
        "label": "INCLUDE", "reason": "", "note": "", "labeled_at": "t",
    })
    la.append_gold(gold, {
        "pmid": "222", "uid": "europepmc:MED:222", "is_decoy": "1",
        "label": "EXCLUDE", "reason": "ET1", "note": "mồi", "labeled_at": "t",
    })
    done = la.read_gold(gold)
    assert set(done) == {"111", "222"}
    assert done["222"]["reason"] == "ET1"
    # Header chỉ ghi một lần.
    with gold.open(encoding="utf-8") as f:
        assert sum(1 for row in csv.reader(f)) == 3


def test_load_input_accepts_csv_and_json(tmp_path):
    rows = [{"pmid": "1", "title": "T", "abstract": "A", "is_decoy": "0"}]
    j = tmp_path / "in.json"
    j.write_text(json.dumps(rows), encoding="utf-8")
    assert la.load_input(j)[0]["pmid"] == "1"

    c = tmp_path / "in.csv"
    with c.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pmid", "title", "abstract", "is_decoy"])
        w.writeheader()
        w.writerows(rows)
    assert la.load_input(c)[0]["pmid"] == "1"


def test_load_input_rejects_row_without_pmid(tmp_path):
    j = tmp_path / "in.json"
    j.write_text(json.dumps([{"title": "T", "abstract": "A"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="pmid"):
        la.load_input(j)


# --- Nghiệm thu ------------------------------------------------------------------------


def _seed(store, uid, va, vb):
    doc = Document(uid=uid, source="europepmc", source_id=uid, authority_tier=1, title="t")
    doc.status = DocStatus.QUEUED
    store.upsert(doc)
    store.add_screen_verdict(uid, "screener_a", "m1", va, None, "q", "high")
    store.add_screen_verdict(uid, "screener_b", "m2", vb, None, "q", "high")


def _gold_rows(spec):
    return {
        pmid: {
            "pmid": pmid, "uid": f"europepmc:MED:{pmid}", "is_decoy": decoy,
            "label": label, "reason": "", "note": "", "labeled_at": "t",
        }
        for pmid, label, decoy in spec
    }


def test_report_flags_kappa_below_floor(store):
    """Máy đồng thuận với nhau nhưng lệch người ⇒ phải KHÔNG ĐẠT."""
    spec = []
    for i in range(6):
        pmid = f"1000000{i}"
        _seed(store, f"europepmc:MED:{pmid}", "include", "include")
        # Người loại một nửa — máy nhận hết.
        spec.append((pmid, "INCLUDE" if i < 3 else "EXCLUDE", "0"))
    gold = _gold_rows(spec)
    uids = [r["uid"] for r in gold.values()]
    report = la.acceptance_report(gold, la.machine_verdicts(store, uids))

    assert "screener_a ↔ người" in report
    assert "KHÔNG ĐẠT" in report


def test_report_catches_degenerate_include_all(store):
    """Đồng thuận thoái hóa: máy nhận 100% ⇒ include-rate phải bị đánh KHÔNG ĐẠT.

    Đây là ca κ đơn độc MÙ — cả hai run E2E thật đều rơi vào dạng này.
    """
    spec = []
    for i in range(5):
        pmid = f"2000000{i}"
        _seed(store, f"europepmc:MED:{pmid}", "include", "include")
        spec.append((pmid, "INCLUDE", "0"))
    gold = _gold_rows(spec)
    report = la.acceptance_report(gold, la.machine_verdicts(store, [r["uid"] for r in gold.values()]))

    assert "Include-rate" in report
    assert "100.0%" in report
    assert "KHÔNG ĐẠT" in report


def test_report_scores_decoy_rejection(store):
    spec = []
    for i in range(4):
        pmid = f"3000000{i}"
        # Máy loại 3/4 mồi.
        verdict = "exclude" if i < 3 else "include"
        _seed(store, f"europepmc:MED:{pmid}", verdict, verdict)
        spec.append((pmid, "EXCLUDE", "1"))
    gold = _gold_rows(spec)
    report = la.acceptance_report(gold, la.machine_verdicts(store, [r["uid"] for r in gold.values()]))

    assert "Mồi bị loại đúng" in report
    assert "3/4" in report


def test_report_without_machine_verdicts_says_so(store):
    gold = _gold_rows([("40000001", "INCLUDE", "0")])
    report = la.acceptance_report(gold, {})
    assert "Chưa có phán định máy" in report


def test_include_rate_ignores_invalid_verdicts():
    assert la.include_rate(["include", "exclude", "VOID"]) == 0.5
    assert la.include_rate(["VOID"]) is None
