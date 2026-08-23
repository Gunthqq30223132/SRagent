"""Test sổ đăng ký nguồn MỞ — thay cho danh sách trắng khóa cứng 2 nguồn.

Quyết định 2026-08-23 của chủ dự án: gỡ ràng buộc chỉ-arXiv-và-IEEE.
Tầm nhìn: SR-Agent là bộ máy sinh chứng cứ dùng chung, đổi nguồn tham khảo là
có hệ tri thức hệ thống cho lĩnh vực khác. Nguồn vì thế phải là dữ liệu đăng
ký được, không phải hằng số biên dịch.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from sr_agent.config import (
    AUTHORITY_TIERS,
    ID_PATTERNS,
    UNKNOWN_SOURCE_TIER,
    register_source,
    registered_sources,
)
from sr_agent.models.schemas import Document, default_tier


def make(source: str, source_id: str, tier: int | None = None) -> Document:
    return Document(
        uid="", source=source, source_id=source_id,
        authority_tier=tier if tier is not None else default_tier(source),
        title="Tài liệu thử",
    )


@pytest.fixture
def so_dang_ky_sach():
    """Khôi phục sổ đăng ký sau mỗi test — nó là trạng thái toàn cục."""
    tiers, patterns = dict(AUTHORITY_TIERS), dict(ID_PATTERNS)
    yield
    AUTHORITY_TIERS.clear(); AUTHORITY_TIERS.update(tiers)
    ID_PATTERNS.clear(); ID_PATTERNS.update(patterns)


class TestNguonMoiChayNgay:
    def test_nguon_chua_dang_ky_van_tao_duoc_document(self):
        """Đây chính là ràng buộc vừa được gỡ: trước đây ValidationError."""
        doc = make("cochrane", "CD012345")
        assert doc.uid == "cochrane:CD012345"

    def test_nguon_la_nhan_tier_thap_nhat(self):
        assert make("blog-nao-do", "abc").authority_tier == UNKNOWN_SOURCE_TIER

    def test_nguon_la_khong_bi_kiem_quy_tac_id(self):
        """Chưa khai quy tắc thì không có gì để kiểm — không được bịa ra luật."""
        assert make("nguon-moi", "id-dinh-dang-la-gi-cung-duoc").source_id

    def test_source_rong_bi_tu_choi(self):
        # Tài liệu không có nguồn thì không truy vết được — đây là ranh giới
        # DUY NHẤT còn giữ sau khi mở khóa.
        with pytest.raises(ValidationError):
            make("   ", "abc")

    def test_source_duoc_chuan_hoa_ve_chu_thuong(self):
        assert make("PubMed", "pubmed:123").source == "pubmed"


class TestDangKyNguon:
    def test_dang_ky_xong_thi_quy_tac_id_co_hieu_luc(self, so_dang_ky_sach):
        register_source("cochrane", id_pattern=r"^CD\d{6}$", authority_tier=1)
        assert make("cochrane", "CD012345").authority_tier == 1
        with pytest.raises(ValidationError):
            make("cochrane", "sai-dinh-dang")

    def test_dang_ky_nang_tier_len(self, so_dang_ky_sach):
        truoc = default_tier("embase")
        register_source("embase", authority_tier=1)
        assert truoc == UNKNOWN_SOURCE_TIER and default_tier("embase") == 1

    def test_dang_ky_trung_ten_khac_tier_thi_noi_ngay(self, so_dang_ky_sach):
        """Nổ lúc nạp module, không phải lúc dữ liệu đã vào kho."""
        register_source("nguon-x", authority_tier=1)
        with pytest.raises(ValueError):
            register_source("nguon-x", authority_tier=3)

    def test_dang_ky_lai_y_het_thi_bo_qua_im_lang(self, so_dang_ky_sach):
        register_source("nguon-y", authority_tier=2)
        register_source("nguon-y", authority_tier=2)
        assert AUTHORITY_TIERS["nguon-y"] == 2

    def test_overwrite_cho_phep_doi_co_y(self, so_dang_ky_sach):
        register_source("nguon-z", authority_tier=4)
        register_source("nguon-z", authority_tier=1, overwrite=True)
        assert AUTHORITY_TIERS["nguon-z"] == 1

    def test_ten_rong_bi_tu_choi(self, so_dang_ky_sach):
        with pytest.raises(ValueError):
            register_source("  ")

    def test_nhan_ca_chuoi_lan_pattern_da_bien_dich(self, so_dang_ky_sach):
        register_source("nguon-a", id_pattern=r"^A\d+$")
        register_source("nguon-b", id_pattern=re.compile(r"^B\d+$"))
        assert make("nguon-a", "A1").uid and make("nguon-b", "B2").uid


class TestNguonCuKhongDoi:
    """Mở khóa không được làm lỏng quy tắc của hai nguồn đã có."""

    def test_ieee_van_bat_buoc_8_chu_so(self):
        with pytest.raises(ValidationError):
            make("ieee", "1234567")

    def test_arxiv_van_bat_buoc_tien_to(self):
        with pytest.raises(ValidationError):
            make("arxiv", "2401.12345")

    def test_tier_cu_giu_nguyen(self):
        assert (default_tier("ieee"), default_tier("arxiv")) == (1, 2)

    def test_pubmed_da_tu_dang_ky_khi_nap_module(self):
        import tools.sources.pubmed  # noqa: F401
        assert "pubmed" in registered_sources()
        assert default_tier("pubmed") == 1
