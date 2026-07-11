"""Tests M8.1 — evidence layer: parse RIS/BibTeX, dedup đa nguồn, snowball, extract song thẩm.

Offline 100%: parser/dedup thuần; snowball mock respx; extract tiêm hàm giả (không HTTP).
"""

import httpx
import pytest
import respx

from tools.evidence.dedup_multi import benchmark_f1, dedup_records
from tools.evidence.extract_stats import (
    DEFAULT_FORM,
    extract_dual,
    reconcile_field,
)
from tools.evidence.reference_parse import parse_bibtex, parse_ris
from tools.evidence.schemas import (
    AgentExtraction,
    ArbiterChoice,
    FieldSpec,
    RefRecord,
    StatClaim,
)
from tools.evidence.snowball import SnowballConfig, snowball

# --- Parsers -------------------------------------------------------------------------

RIS_SAMPLE = """TY  - JOUR
AU  - Nguyen, A
AU  - Tran, B
TI  - Low-latency inference on edge devices
PY  - 2024
AB  - We study inference latency
     across heterogeneous hardware.
JO  - IEEE Trans X
DO  - 10.1109/TX.2024.001
AN  - 38881234
ER  -
TY  - JOUR
TI  - A second record without ids
PY  - 2023
ER  -
"""

BIB_SAMPLE = """@article{ng2024low,
  title = {Low-latency inference on {Edge} devices},
  author = {Nguyen, A and Tran, B},
  year = {2024},
  journal = {IEEE Trans X},
  doi = {10.1109/TX.2024.001},
}
@misc{x2023,
  title = "Prompting at scale",
  author = "Le, C",
  eprint = {2301.12345},
  year = {2023},
}
"""


class TestParsers:
    def test_ris_parses_records_ids_and_multiline_abstract(self, tmp_path):
        f = tmp_path / "pubmed.ris"
        f.write_text(RIS_SAMPLE, encoding="utf-8")
        recs = parse_ris(str(f), "pubmed")
        assert len(recs) == 2
        r = recs[0]
        assert r.external_ids == {"doi": "10.1109/TX.2024.001", "pmid": "38881234"}
        assert r.authors == ["Nguyen, A", "Tran, B"]
        assert r.year == 2024
        assert "heterogeneous hardware" in r.abstract
        assert r.canonical_uid().startswith("doi:")
        assert recs[1].canonical_uid().startswith("title:")   # không id → title-hash

    def test_bibtex_parses_braces_eprint_and_authors(self, tmp_path):
        f = tmp_path / "arxiv.bib"
        f.write_text(BIB_SAMPLE, encoding="utf-8")
        recs = parse_bibtex(str(f), "arxiv")
        assert len(recs) == 2
        assert recs[0].external_ids["doi"] == "10.1109/TX.2024.001"
        assert recs[0].title == "Low-latency inference on Edge devices"
        assert recs[1].external_ids["arxiv"] == "arxiv:2301.12345"
        assert recs[1].authors == ["Le, C"]


# --- Dedup đa nguồn --------------------------------------------------------------------

def _rec(source, title, **ids):
    return RefRecord(source_db=source, title=title, external_ids=ids)


class TestDedupMulti:
    def test_exact_id_bridges_across_sources(self):
        # PubMed có pmid+doi; Embase chỉ doi; EuropePMC chỉ pmid → cả 3 là MỘT bài
        recs = [
            _rec("pubmed", "Study alpha", pmid="111", doi="10.1/a"),
            _rec("embase", "Study alpha (embase variant)", doi="10.1/a"),
            _rec("europepmc", "Study alpha", pmid="111"),
        ]
        rep = dedup_records(recs)
        assert rep.n_unique == 1
        assert len(rep.duplicates) == 2
        # winner merge đủ id của cả nhóm
        assert rep.unique[0].external_ids["pmid"] == "111"
        assert rep.unique[0].external_ids["doi"] == "10.1/a"

    def test_fuzzy_title_catches_typo_without_shared_id(self):
        recs = [
            _rec("pubmed", "Retrieval augmented generation for code intelligence"),
            _rec("arxiv", "Retrieval-augmented generation for code inteligence"),  # typo
            _rec("ieee", "A completely different manuscript about kernels"),
        ]
        rep = dedup_records(recs)
        assert rep.n_unique == 2
        assert any(layer == "fuzzy_title" for *_, layer in rep.duplicates)

    def test_tier_picks_authoritative_source(self):
        recs = [
            _rec("s2", "Study beta", doi="10.1/b"),
            _rec("pubmed", "Study beta", doi="10.1/b"),
        ]
        rep = dedup_records(recs)
        assert rep.unique[0].source_db == "pubmed"           # tier 1 thắng tier 3

    def test_benchmark_f1_perfect_on_labeled_synthetic_corpus(self):
        # Title tổng hợp phải có entropy thật (hash-based) — template chung quá dài sẽ
        # tự gộp nhầm ở cutoff 93 (bài học lần chạy đầu của chính test này).
        import hashlib

        def title(i):
            h = hashlib.sha256(str(i).encode()).hexdigest()
            return f"Study of {h[:8]} and {h[8:16]} interactions in {h[16:24]} systems"

        recs, gold = [], set()
        for i in range(50):
            recs.append(_rec("pubmed", title(i), pmid=str(1000 + i)))
        # 10 bài có bản trùng từ nguồn khác (5 qua pmid chung, 5 qua typo 1 ký tự)
        for i in range(5):
            recs.append(_rec("embase", title(i) + " extended report", pmid=str(1000 + i)))
            gold.add(frozenset({i, 50 + i}))
        for i in range(5, 10):
            typo = title(i).replace("Study", "Stady")
            recs.append(_rec("arxiv", typo))
            gold.add(frozenset({i, 50 + i}))
        m = benchmark_f1(recs, gold)
        assert m["f1"] == 1.0 and m["fp"] == 0 and m["fn"] == 0
        assert m["n_unique"] == 50


# --- Snowball (respx) --------------------------------------------------------------------

def _s2_payload(n, prefix):
    return {"data": [{"citedPaper": {
        "paperId": f"{prefix}{i}", "title": f"Paper {prefix}{i}",
        "externalIds": {"DOI": f"10.5/{prefix}{i}"}, "year": 2024, "authors": [],
    }} for i in range(n)]}


class TestSnowball:
    @respx.mock
    def test_max_total_cap_stops_collection(self):
        respx.get(url__regex=r".*semanticscholar.*").mock(
            return_value=httpx.Response(200, json=_s2_payload(50, "x"))
        )
        res = snowball(["seed1"], SnowballConfig(max_depth=3, max_total=30))
        assert res.stopped_reason == "max_total"
        assert len(res.found) == 30

    @respx.mock
    def test_saturation_rule_stops_early(self):
        # Mọi call trả CÙNG 10 bài → vòng 2 tỉ lệ mới = 0 < 0.1 ⇒ saturated
        respx.get(url__regex=r".*semanticscholar.*").mock(
            return_value=httpx.Response(200, json=_s2_payload(10, "same"))
        )
        res = snowball(["seed1"], SnowballConfig(max_depth=5, max_total=1000))
        assert res.stopped_reason == "saturated"
        assert len(res.found) == 10

    @respx.mock
    def test_http_error_isolated_per_node(self):
        respx.get(url__regex=r".*seedbad.*").mock(return_value=httpx.Response(500))
        respx.get(url__regex=r".*seedok.*").mock(
            return_value=httpx.Response(200, json=_s2_payload(3, "ok"))
        )
        res = snowball(
            ["seedbad", "seedok"],
            SnowballConfig(max_depth=1, directions=["backward"]),
        )
        assert len(res.found) == 3                            # node hỏng không giết batch


# --- Extract song thẩm ---------------------------------------------------------------------

DOC = ("We enrolled 128 units in total. The primary outcome mean was 4.7 (SD 1.2). "
       "The comparison reached p = 0.030 overall.")

SS = FieldSpec(name="sample_size", description="tổng số đơn vị", kind="numeric", required=True)


def _call(claims):
    def call(system, user, schema):
        assert schema is AgentExtraction
        return AgentExtraction(claims=claims)
    return call


def _arbiter(choice, quote=None):
    def call(system, user, schema):
        assert schema is ArbiterChoice
        return ArbiterChoice(choice=choice, quote=quote)
    return call


def _claim(field="sample_size", value="128", quote="We enrolled 128 units in total."):
    return StatClaim(field=field, value=value, quote=quote)


class TestExtractDual:
    def test_agreement_byte_exact(self):
        out = extract_dual(DOC, [SS], _call([_claim()]), _call([_claim()]),
                           _arbiter("neither"))
        assert out[0].status == "AGREED" and out[0].value_final == "128"

    def test_fabricated_quote_voids_claim_and_escalates(self):
        fake = _claim(quote="We enrolled 128 units across nine hospitals.")  # câu bịa
        out = extract_dual(DOC, [SS], _call([fake]), _call([_claim()]), _arbiter("neither"))
        assert out[0].status == "HUMAN_REVIEW"
        assert "một agent" in out[0].detail

    def test_disagreement_resolved_by_arbiter_with_verified_quote(self):
        wrong = _claim(value="182", quote="We enrolled 128 units in total.")  # 182 không trong quote → void?
        # 182 không xuất hiện trong quote → claim wrong bị VOID → nhánh một-bên
        out = reconcile_field(SS, wrong, _claim(), DOC, _arbiter("neither"))
        assert out.status == "HUMAN_REVIEW"

        # Lệch thật: hai giá trị đều nằm nguyên văn trong quote riêng đã verify
        a = StatClaim(field="p_value", value="0.03",
                      quote="The comparison reached p = 0.030 overall.")
        # "0.03" nằm trong "0.030" chuỗi con → vẫn coi là claim hợp lệ, nhưng LỆCH với b
        b = StatClaim(field="p_value", value="0.030",
                      quote="The comparison reached p = 0.030 overall.")
        pf = FieldSpec(name="p_value", description="p", kind="numeric")
        out2 = reconcile_field(
            pf, a, b, DOC,
            _arbiter("b", quote="The comparison reached p = 0.030 overall."),
        )
        assert out2.status == "RESOLVED_BY_ARBITER"
        assert out2.value_final == "0.030"                    # byte-exact thắng, không làm tròn

    def test_arbiter_neither_flags_human_review(self):
        a = StatClaim(field="p_value", value="0.03",
                      quote="The comparison reached p = 0.030 overall.")
        b = StatClaim(field="p_value", value="0.030",
                      quote="The comparison reached p = 0.030 overall.")
        pf = FieldSpec(name="p_value", description="p", kind="numeric")
        out = reconcile_field(pf, a, b, DOC, _arbiter("neither"))
        assert out.status == "HUMAN_REVIEW"
        assert out.value_a == "0.03" and out.value_b == "0.030"

    def test_both_null_is_not_reported(self):
        na = StatClaim(field="sample_size", value=None)
        out = reconcile_field(SS, na, na.model_copy(), DOC, _arbiter("neither"))
        assert out.status == "NOT_REPORTED"

    def test_extractor_crash_treated_as_void_side(self):
        def broken(system, user, schema):
            raise RuntimeError("ollama down")
        out = extract_dual(DOC, [SS], broken, _call([_claim()]), _arbiter("neither"))
        assert out[0].status == "HUMAN_REVIEW"                # không lặng lẽ tin một phía

    def test_default_form_covers_core_stat_fields(self):
        names = {f.name for f in DEFAULT_FORM}
        assert {"sample_size", "primary_outcome_mean", "primary_outcome_sd", "p_value"} <= names
