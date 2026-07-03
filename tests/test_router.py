import pytest

from sr_agent.errors import UnsupportedFormat
from sr_agent.ingest.router import SourceRouter


@pytest.fixture
def router():
    return SourceRouter(fetchers={"ieee": object(), "arxiv": object()})


def test_classify_ieee(router):
    assert router.classify("38111222") == ("ieee", "38111222")


def test_classify_arxiv_variants(router):
    assert router.classify("arxiv:2401.12345") == ("arxiv", "arxiv:2401.12345")
    assert router.classify("2401.12345v2") == ("arxiv", "arxiv:2401.12345")


def test_unknown_id_rejected(router):
    with pytest.raises(UnsupportedFormat):
        router.classify("doi:10.1145/3576915")
    with pytest.raises(UnsupportedFormat):
        router.classify("1234567")  # 7 chữ số — lệch quy tắc 8 số


def test_unknown_source_rejected(router):
    with pytest.raises(UnsupportedFormat):
        router.fetcher_for("semanticscholar")
