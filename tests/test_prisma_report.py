"""Tests for tools/prisma_report.py."""

import json
from datetime import datetime, timezone
import pytest

from sr_agent.models.schemas import DocStatus
from sr_agent.store.staging import StagingStore
from tests.test_pipeline import make_doc
from tools.prisma_report import generate_prisma_report


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


def test_prisma_report_counts(store):
    # 1. Setup mock runs
    report1 = {"fetched": 5, "duplicates": 1, "rejected_by_rubric": 2, "queued": 2}
    store.record_run("query1", datetime.now(timezone.utc).isoformat(), json.dumps(report1))
    
    # 2. Setup mock screening
    # Document 1: include
    doc1 = make_doc("ieee", "11111111", "Title 1", 1)
    doc1.status = DocStatus.QUEUED
    store.upsert(doc1)
    store.add_screen_verdict("ieee:11111111", "screener_a", "m1", "include", confidence="high")
    
    # Document 2: exclude
    doc2 = make_doc("ieee", "22222222", "Title 2", 1)
    doc2.status = DocStatus.QUEUED
    store.upsert(doc2)
    store.add_screen_verdict("ieee:22222222", "screener_a", "m1", "exclude", "ET1", "quote 2", "high")
    
    # 3. Setup mock approved
    doc3 = make_doc("ieee", "33333333", "Title 3", 1)
    doc3.status = DocStatus.APPROVED
    store.upsert(doc3)
    
    report = generate_prisma_report(store)
    
    # Assert identified: 5 (from runs)
    assert "- **Records identified from databases**: 5" in report
    # Assert duplicates: 1
    assert "- **Duplicate records removed**: 1" in report
    # Assert rubric excluded: 2
    assert "- **Records excluded by quality gate (rubric < 60)**: 2" in report
    # Assert screened: 2
    assert "- **Records screened**: 2" in report
    # Assert excluded: 1
    assert "- **Records excluded**: 1" in report
    # Assert inclusion: 1
    assert "- **Studies included in systematic review**: 1" in report
    # Assert specific exclusion reasons
    assert "- **ET1**: 1 records" in report


# --- Không đo được phải kêu VÔ HIỆU, không được trả 0 (luật L3) -------------------------

def test_khong_co_du_lieu_thi_bao_VO_HIEU_chu_khong_bao_0(store):
    """Kho rỗng: '0 bản trùng bị loại' và 'chưa ai đo bản trùng' KHÔNG được in giống nhau."""
    report = generate_prisma_report(store)
    assert "VÔ HIỆU" in report
    assert "- **Records identified from databases**: 0" not in report
    assert "- **Duplicate records removed**: 0" not in report


def test_du_phong_dem_dung_ten_su_kien_pipeline_dang_ghi(store):
    """Không có runs -> phải đếm được qua events, bằng ĐÚNG tên pipeline ghi ra."""
    store.log_event("ieee:11111111", "DEDUP_DROPPED", "trùng mờ với ieee:22222222 (score=97.0)")
    store.log_event("ieee:33333333", "DEDUP_MERGED", "thay thế arxiv:2401.1 (tier ưu tiên)")

    report = generate_prisma_report(store)
    assert "- **Duplicate records removed**: 2" in report
    # Trùng tầng 1 không được pipeline ghi sự kiện -> con số này là SÀN, phải nói ra
    assert "SÀN" in report


def test_ten_su_kien_cu_da_chet_khong_con_duoc_tin(store):
    """'DUPLICATE_ID'/'FETCHED' là tên KHÔNG AI GHI — không được lấy làm căn cứ."""
    store.log_event("ieee:11111111", "DUPLICATE_ID", "tên cũ, không nơi nào trong kho ghi ra")
    store.log_event("ieee:22222222", "FETCHED", "tên cũ, không nơi nào trong kho ghi ra")

    report = generate_prisma_report(store)
    assert "- **Duplicate records removed**: 1" not in report
    assert "- **Records identified from databases**: 1" not in report
    assert "VÔ HIỆU" in report


def test_so_do_mermaid_khong_vo_cu_phap_khi_VO_HIEU(store):
    """Nhãn VÔ HIỆU không được mang dấu ngoặc vuông — sẽ làm hỏng nút mermaid."""
    report = generate_prisma_report(store)
    so_do = report.split("```mermaid")[1]
    for dong in so_do.splitlines():
        if "Identified:" in dong or "Duplicates Removed:" in dong:
            assert dong.count("[") == dong.count("]")
            assert "[1 lần chạy]" not in dong
