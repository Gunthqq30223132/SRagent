from sr_agent.dedup.d34 import DedupAction, decide, merge_superseded
from sr_agent.models.schemas import Document


def doc(source, source_id, title, tier):
    return Document(
        uid="", source=source, source_id=source_id, authority_tier=tier, title=title,
    )


IEEE = doc("ieee", "38111222", "Efficient Transformer Inference on Edge Devices", 1)
ARXIV = doc("arxiv", "arxiv:2401.12345", "Efficient Transformer  Inference on Edge Devices!", 2)


def test_layer1_exact_id():
    d = decide(IEEE, {"ieee:38111222"}, {}, {})
    assert d.action is DedupAction.DUPLICATE_ID
    assert d.matched_uid == "ieee:38111222"


def test_layer2_no_match_is_new():
    d = decide(
        IEEE, set(),
        {"a survey of graph neural network acceleration techniques": "ieee:37000111"},
        {"ieee:37000111": 1},
    )
    assert d.action is DedupAction.NEW


def test_layer2_fuzzy_same_tier_is_duplicate():
    # bản arXiv thứ 2 (tier 2) trùng mờ với bản arXiv đã có (tier 2) -> drop
    other = doc("arxiv", "arxiv:2503.99999", "Efficient Transformer Inference on Edge Device", 2)
    d = decide(
        other, set(),
        {ARXIV.title_normalized: ARXIV.uid},
        {ARXIV.uid: 2},
    )
    assert d.action is DedupAction.DUPLICATE_FUZZY
    assert d.matched_uid == ARXIV.uid
    assert d.score >= 93


def test_layer3_higher_tier_supersedes():
    # bản IEEE (tier 1) đến sau, trùng mờ bản arXiv (tier 2) -> thay thế
    d = decide(
        IEEE, set(),
        {ARXIV.title_normalized: ARXIV.uid},
        {ARXIV.uid: 2},
    )
    assert d.action is DedupAction.SUPERSEDES
    assert d.matched_uid == ARXIV.uid


def test_layer3_lower_tier_is_dropped():
    # bản arXiv (tier 2) đến sau, trùng mờ bản IEEE (tier 1) -> drop
    d = decide(
        ARXIV, set(),
        {IEEE.title_normalized: IEEE.uid},
        {IEEE.uid: 1},
    )
    assert d.action is DedupAction.DUPLICATE_FUZZY


def test_merge_keeps_trace_and_fills_metadata():
    winner = doc("ieee", "38111222", "Efficient Transformer Inference on Edge Devices", 1)
    loser = doc("arxiv", "arxiv:2401.12345", "Efficient Transformer Inference on Edge Devices", 2)
    loser.abstract = "preprint abstract"
    loser.authors = ["Alice Nguyen"]

    merged = merge_superseded(winner, loser)
    assert merged.alternate_uids == ["arxiv:2401.12345"]
    assert merged.abstract == "preprint abstract"  # bù metadata thiếu
    assert merged.authors == ["Alice Nguyen"]


def test_determinism_same_input_same_output():
    args = (IEEE, set(), {ARXIV.title_normalized: ARXIV.uid}, {ARXIV.uid: 2})
    assert all(decide(*args) == decide(*args) for _ in range(5))


# --- Tầng 1 phải đọc alternate_uids -----------------------------------------------------
#
# Ca thật ghi ở docs/SO_CO_CHE.md:127-129: phiếu ghi `pubmed:26095867` còn Europe PMC trả
# `europepmc:MED:26095867`. So thẳng hai chuỗi uid sẽ KHÔNG khớp, dù đó là một bài.

def doc_epmc_co_dinh_danh_khac(title="Perioperative anticoagulation management", alt=None):
    return Document(
        uid="", source="europepmc", source_id="europepmc:MED:26095867",
        authority_tier=1, title=title,
        alternate_uids=["pubmed:26095867"] if alt is None else alt,
    )


def test_tang1_bat_duoc_dinh_danh_khac_cua_cung_mot_bai():
    """Bản Europe PMC gặp bản PubMed đã có trong kho -> phải là MỘT bài."""
    d = decide(doc_epmc_co_dinh_danh_khac(), {"pubmed:26095867"}, {}, {})
    assert d.action is DedupAction.DUPLICATE_ID
    assert d.matched_uid == "pubmed:26095867"  # trả uid ĐANG CÓ trong kho, không phải uid mới


def test_tang1_khong_bat_oan_khi_dinh_danh_khac_khong_co_trong_kho():
    """Cổng hay báo oan là cổng sẽ bị bỏ qua — không được bắt nhầm bài chưa có."""
    d = decide(doc_epmc_co_dinh_danh_khac(), {"pubmed:99999999"}, {}, {})
    assert d.action is DedupAction.NEW


def test_tang1_dinh_danh_khac_tat_dinh_khi_nhieu_cai_cung_khop():
    """Nhiều alternate_uids cùng khớp -> vẫn phải luôn trả về cùng một kết quả."""
    nhieu = doc_epmc_co_dinh_danh_khac(alt=["pubmed:26095867", "doi:10.1000/abc"])
    kho = {"pubmed:26095867", "doi:10.1000/abc"}
    ket_qua = {decide(nhieu, kho, {}, {}).matched_uid for _ in range(20)}
    assert ket_qua == {"pubmed:26095867"}  # cái đầu trong list, không phụ thuộc thứ tự set


def test_LO_HONG_CON_TON_chieu_nguoc_chua_bat_duoc():
    """Chiều ngược lại VẪN HỎNG — giữ kiểm thử này để lỗ hổng có vết, không bị quên.

    Ở đây bản ghi ĐÃ CÓ trong kho mới là bản mang alternate_uids. `decide()` chỉ nhận
    `existing_uids` (tập uid chuẩn), không nhận alternate_uids của bản đã có, nên không
    thấy được. Vá chiều này phải dựng thêm một chỉ mục ở BÊN GỌI — mà bên gọi là
    `sr_agent/pipeline.py`, nằm trong vùng cấm zero-touch của luật L2.

    Khi nào Gun mở ngoại lệ L2: đổi assert dưới thành DUPLICATE_ID và xoá kiểm thử này.
    """
    moi = Document(
        uid="", source="pubmed", source_id="pubmed:26095867",
        authority_tier=1, title="Perioperative anticoagulation management",
    )
    # Kho đang có bản Europe PMC, và chính NÓ mang alternate_uids ["pubmed:26095867"].
    d = decide(moi, {"europepmc:MED:26095867"}, {}, {})
    assert d.action is DedupAction.NEW, "nếu ca này đã bắt được thì lỗ hổng đã vá — cập nhật kiểm thử"
