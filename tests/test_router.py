import pytest

from sr_agent.errors import UnsupportedFormat
from sr_agent.ingest.router import SourceRouter


@pytest.fixture
def router():
    return SourceRouter(fetchers={
        "ieee": object(), "arxiv": object(), "europepmc": object(),
    })


def test_classify_ieee(router):
    assert router.classify("38111222") == ("ieee", "38111222")


def test_classify_europepmc_variants(router):
    assert router.classify("europepmc:MED:38111222") == (
        "europepmc", "europepmc:MED:38111222")
    assert router.classify("MED/38111222") == ("europepmc", "europepmc:MED:38111222")
    assert router.classify("PMC9000111") == ("europepmc", "europepmc:PMC:9000111")


def test_bare_8_digits_stays_ieee_not_europepmc(router):
    # Bảo vệ tính tất định: PMID số trần KHÔNG được EPMC nuốt mất khỏi ieee.
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
