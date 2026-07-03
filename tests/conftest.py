import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ieee_search_json() -> dict:
    return json.loads((FIXTURES / "ieee_search.json").read_text())


@pytest.fixture
def arxiv_atom_xml() -> str:
    return (FIXTURES / "arxiv_atom.xml").read_text()
