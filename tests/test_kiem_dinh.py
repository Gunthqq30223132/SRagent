"""Test cổng kiểm định trên PHIẾU THẬT do Spark tạo (2026-08-23).

Fixture tests/fixtures/phieu_spark_that.json là bản tải nguyên vẹn từ Drive,
không sửa một byte. Đây là dữ liệu hồi quy quý nhất hiện có: nó ghi lại chính
xác Spark làm được gì và không làm được gì ở lần chạy thật đầu tiên.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.sources.hang_doi import PhieuQuet, doc_hang_doi

FIXTURE = Path(__file__).parent / "fixtures" / "phieu_spark_that.json"


class TestPhieuSparkThat:
    def test_phieu_that_qua_cong(self, tmp_path):
        """Lần chạy đầu của cơ chế mới: 0 lỗi cấu trúc."""
        shutil.copy(FIXTURE, tmp_path / FIXTURE.name)
        kq = doc_hang_doi(tmp_path)
        assert len(kq.phieu_hop_le) == 1 and kq.phieu_hong == []

    def test_ma_pmid_khong_bi_ep_kieu(self):
        """Vòng lặp cũ hỏng mã ở 22/22 dòng vì Sheets. JSON giữ nguyên vẹn."""
        p = PhieuQuet.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
        assert p.ids == ["pubmed:40448969", "pubmed:34108229",
                         "pubmed:26095867", "pubmed:36462533"]

    def test_so_hoc_nhat_quan(self):
        p = PhieuQuet.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
        assert len(p.ids) + len(p.loai_tru) <= p.so_da_sang <= p.so_ket_qua_tho

    def test_truy_van_la_boolean_that(self):
        p = PhieuQuet.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
        assert "[Mesh]" in p.chuoi_truy_van and " AND " in p.chuoi_truy_van

    def test_moi_ly_do_loai_tru_deu_la_cau_doc_duoc(self):
        p = PhieuQuet.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
        assert all(len(b.ly_do.split()) >= 5 for b in p.loai_tru)

    def test_do_phu_duoi_nguong_he_thong(self):
        """Phiếu HỢP LỆ nhưng độ phủ 0,57% — hợp lệ khác với đủ để làm tổng quan.

        Đây là phát hiện quan trọng nhất của lần chạy: chất lượng bài giữ lại
        xuất sắc, mà độ phủ vẫn gần bằng không. Hai thứ đó độc lập nhau.
        """
        from tools.kiem_dinh import NGUONG_DO_PHU
        p = PhieuQuet.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
        assert p.so_da_sang / p.so_ket_qua_tho < NGUONG_DO_PHU


class TestKhopMaQuaVetDinhDanh:
    """Chống BÁO ĐỘNG GIẢ khi xác minh qua Europe PMC thay vì PubMed.

    Phiếu ghi 'pubmed:26095867'; Europe PMC trả 'europepmc:MED:26095867'. So
    thẳng hai chuỗi sẽ báo sót toàn bộ và kết tội Spark bịa mã, trong khi bài có
    thật. Một cổng hay báo oan là cổng sẽ bị bỏ qua.
    """

    @staticmethod
    def _doc(source_id: str, khac: list[str] | None = None):
        from sr_agent.models.schemas import Document
        return Document(uid="", source="europepmc", source_id=source_id,
                        authority_tier=1, alternate_uids=khac or [], title="Bài")

    def test_khop_qua_alternate_uids(self):
        from tools.kiem_dinh import ma_khong_tim_thay
        d = self._doc("europepmc:MED:26095867", ["pubmed:26095867"])
        assert ma_khong_tim_thay(["pubmed:26095867"], [d]) == []

    def test_khop_ca_khi_khong_co_alternate(self):
        """Khớp phần số đuôi là lưới đỡ khi bản ghi thiếu vết định danh phụ."""
        from tools.kiem_dinh import ma_khong_tim_thay
        d = self._doc("europepmc:MED:26095867")
        assert ma_khong_tim_thay(["pubmed:26095867"], [d]) == []

    def test_ma_that_su_thieu_van_bi_bat(self):
        """Nới lỏng khớp KHÔNG được làm mất khả năng bắt mã bịa."""
        from tools.kiem_dinh import ma_khong_tim_thay
        d = self._doc("europepmc:MED:26095867", ["pubmed:26095867"])
        assert ma_khong_tim_thay(
            ["pubmed:26095867", "pubmed:99999999"], [d]) == ["pubmed:99999999"]

    def test_khong_co_ban_ghi_nao_thi_sot_het(self):
        from tools.kiem_dinh import ma_khong_tim_thay
        assert ma_khong_tim_thay(["pubmed:1", "pubmed:2"], []) == [
            "pubmed:1", "pubmed:2"]
