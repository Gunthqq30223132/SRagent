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
