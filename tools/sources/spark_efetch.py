"""Nhận BẢN GỐC THÔ do Spark tải hộ, khi SR-Agent không tự với tới nguồn.

VÌ SAO CÓ TỆP NÀY — tự vặn lại nguyên tắc "Spark là trinh sát, không phải nguồn":

Nguyên tắc đó đúng, nhưng nó gộp ba việc rất khác nhau vào một chữ "nguồn":
  1. LẤY byte thô từ máy chủ
  2. PHÂN TÍCH byte đó thành trường dữ liệu
  3. DIỄN GIẢI/TÓM TẮT nội dung

Mối nguy thật nằm ở (2) và (3) — nơi một mô hình ngôn ngữ có thể lặng lẽ đổi một
chữ số. Việc (1) chỉ là vận chuyển. Cấm Spark làm (1) trong khi ta KHÔNG CÓ đường
nào khác tới nguồn không làm hệ thống an toàn hơn — nó chỉ làm hệ thống đứng yên.

Nên hợp đồng ở đây là: Spark được phép làm (1), TUYỆT ĐỐI không làm (2) và (3).
Nó nộp lại XML nguyên vẹn từng byte. Bộ phân tích vẫn là bộ phân tích của ta.

CÁI GIÁ, nói thẳng: ta không chứng minh được XML này thật sự đến từ NCBI. Nên
bản ghi thu theo đường này mang nguồn RIÊNG 'pubmed-qua-spark', hạng uy tín 3
thay vì 1. Hệ quả tự động, không cần mã thêm:
  - Tầng 3 chống trùng D34 sẽ cho bản 'pubmed' (hạng 1) THAY THẾ bản qua trung
    gian khi nào ta tự tải được, giữ vết trong alternate_uids.
  - Rubric chấm nó thấp hơn.
Nói cách khác: dùng được ngay để sàng lọc và đọc, nhưng tự động nhường chỗ cho
bản chính thống, và không bao giờ được coi là ngang hàng.
"""

from __future__ import annotations

from pathlib import Path

from sr_agent.config import register_source
from sr_agent.errors import LayoutParseError
from sr_agent.models.schemas import Document
from tools.sources.pubmed import PubMedFetcher

# Hạng 3: dưới tạp chí bình duyệt tự tải (1) và preprint tự tải (2), trên nguồn
# hoàn toàn chưa đăng ký (5). Chưa đối chiếu độc lập thì chưa được hưởng uy tín.
register_source("pubmed-qua-spark", authority_tier=3)


class SparkEfetchReader(PubMedFetcher):
    """Đọc XML efetch do Spark nộp. DÙNG LẠI bộ phân tích của PubMedFetcher.

    Kế thừa chứ không viết lại: nếu bộ phân tích khác nhau thì phép đối chiếu
    sau này sẽ đo nhầm — ta sẽ tưởng Spark làm sai trong khi thật ra hai bộ
    phân tích bất đồng. Chỉ đổi đúng tên nguồn.
    """

    source = "pubmed-qua-spark"

    def __init__(self) -> None:
        super().__init__(client=None, api_key="", email="")

    def doc_tep(self, duong_dan: Path) -> list[Document]:
        noi_dung = duong_dan.read_text(encoding="utf-8")
        return self.parse_efetch_xml(noi_dung)


def doi_chieu_voi_phieu(docs: list[Document], ids_phieu: list[str]) -> list[str]:
    """So bản ghi thu được với danh sách ID Spark đã khai trong phiếu.

    Đây là chốt chặn rẻ nhất chống việc tráo nội dung: Spark khai một đằng ở
    phiếu, nộp một nẻo ở XML. Không cần tin ai — chỉ cần hai thứ nó tự nộp phải
    khớp nhau. Lệch ở đâu là báo ở đó.
    """
    def bare(uid: str) -> str:
        return uid.rsplit(":", 1)[-1]

    co_trong_xml = {bare(d.source_id) for d in docs}
    khai_trong_phieu = {bare(i) for i in ids_phieu}

    van_de: list[str] = []
    for thieu in sorted(khai_trong_phieu - co_trong_xml):
        van_de.append(
            f"{thieu}: khai trong phiếu nhưng KHÔNG có trong XML nộp kèm — "
            f"Spark chỉ điểm mà không nộp bản gốc"
        )
    for thua in sorted(co_trong_xml - khai_trong_phieu):
        van_de.append(
            f"{thua}: có trong XML nhưng KHÔNG khai trong phiếu — "
            f"bản ghi lọt vào mà không qua bước sàng lọc nào"
        )
    return van_de


def kiem_toan_ven_xml(docs: list[Document]) -> list[str]:
    """Kiểm tính toàn vẹn tối thiểu của từng bản ghi.

    Không chứng minh được XML đến từ NCBI, nhưng chứng minh được nó CÓ HÌNH
    DẠNG của bản ghi NCBI. Bản ghi thiếu tiêu đề hay thiếu tác giả là dấu hiệu
    của cắt xén hoặc dựng tay, đáng nghi hơn hẳn một bản ghi đầy đủ.
    """
    van_de: list[str] = []
    for d in docs:
        thieu = [ten for ten, co in (
            ("tiêu đề", bool(d.title.strip())),
            ("tóm tắt", bool(d.abstract)),
            ("tác giả", bool(d.authors)),
            ("ngày xuất bản", d.published_date is not None),
        ) if not co]
        if thieu:
            van_de.append(f"{d.source_id}: thiếu {', '.join(thieu)}")
    return van_de


def so_khop_ban_chinh_thong(
    qua_spark: list[Document], tu_nguon: list[Document]
) -> dict[str, list[str]]:
    """ĐỐI CHIẾU: bản Spark nộp vs bản SR-Agent tự tải. Chạy khi có mạng NCBI.

    ĐÂY LÀ MỤC ĐÍCH THẬT của cả tệp này. Tranh cãi "có nên tin Spark tải hộ
    không" là tranh cãi không có lời giải bằng lý lẽ — nhưng có lời giải bằng
    phép đo. Cho Spark tải hộ, giữ lại, rồi khi mạng thông thì tải lại và so
    từng trường. Sau N lần ta có TỶ LỆ SAI LỆCH thật thay vì linh cảm.

    Không xây đường này nghĩa là không bao giờ biết câu trả lời.
    """
    def bare(uid: str) -> str:
        return uid.rsplit(":", 1)[-1]

    ban_goc = {bare(d.source_id): d for d in tu_nguon}
    ket_qua: dict[str, list[str]] = {}

    for d in qua_spark:
        ma = bare(d.source_id)
        goc = ban_goc.get(ma)
        if goc is None:
            ket_qua[ma] = ["KHÔNG TỒN TẠI trên nguồn chính thống — mã bịa"]
            continue
        lech: list[str] = []
        if d.title.strip() != goc.title.strip():
            lech.append(f"tiêu đề lệch:\n      spark: {d.title[:90]}\n      gốc  : {goc.title[:90]}")
        if (d.abstract or "").strip() != (goc.abstract or "").strip():
            a, b = len(d.abstract or ""), len(goc.abstract or "")
            lech.append(f"tóm tắt lệch ({a} ký tự vs {b} ký tự)")
        if d.authors != goc.authors:
            lech.append(f"tác giả lệch ({len(d.authors)} vs {len(goc.authors)})")
        if d.published_date and goc.published_date and (
                d.published_date.date() != goc.published_date.date()):
            lech.append(f"ngày lệch ({d.published_date.date()} vs {goc.published_date.date()})")
        if d.evidence_level != goc.evidence_level:
            lech.append(f"bậc chứng cứ lệch ({d.evidence_level} vs {goc.evidence_level})")
        if lech:
            ket_qua[ma] = lech
    return ket_qua


def raise_neu_rong(docs: list[Document], ten_tep: str) -> None:
    """XML hợp lệ nhưng 0 bản ghi là một lỗi, không phải kết quả rỗng bình thường."""
    if not docs:
        raise LayoutParseError(
            f"{ten_tep}: XML phân tích được nhưng không chứa bản ghi nào. "
            f"Nhiều khả năng Spark nộp nhầm tệp, hoặc efetch trả về khung rỗng."
        )
