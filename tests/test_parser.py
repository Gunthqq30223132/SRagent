import json

import httpx
import pytest
import respx

from sr_agent.errors import SchemaValidationError
from sr_agent.models.schemas import CanonicalRole, Document, TechnicalMetadata
from sr_agent.parser.evaluator import evaluate_document
from sr_agent.parser.heuristic import classify_heading, heuristic_sections, split_sections
from sr_agent.parser.ollama_client import OllamaClient
from sr_agent.parser.structural import StructuralParser

OLLAMA = "http://testollama:11434"

FULL_TEXT = """\
1. Introduction
Deploying transformers on edge devices is hard. We survey the space.

2. Methodology
We benchmark quantization and pruning across 12 architectures.

3. Experiments
Results on GLUE and SQuAD show 3.2x speedup.

4. Conclusion
We acknowledge the study is limited to encoder-only models.
"""


def make_doc(**overrides):
    base = dict(
        uid="", source="ieee", source_id="38111222", authority_tier=1,
        title="Efficient Transformer Inference",
        abstract="Code at https://github.com/example/edge-transformers, "
                 "evaluated on GLUE with 10,000 samples.",
    )
    base.update(overrides)
    return Document(**base)


def ollama_response(content: dict) -> dict:
    return {"message": {"role": "assistant", "content": json.dumps(content)}}


class TestHeuristic:
    def test_classify_headings(self):
        assert classify_heading("1. Introduction") is CanonicalRole.CONTEXT
        assert classify_heading("Proposed Approach") is CanonicalRole.METHOD
        assert classify_heading("Experiments") is CanonicalRole.FINDINGS
        assert classify_heading("Conclusion and Future Work") is CanonicalRole.IMPLICATIONS
        assert classify_heading("Acknowledgements") is None

    def test_split_and_assign_full_imrad(self):
        doc = make_doc(full_text=FULL_TEXT)
        roles = heuristic_sections(doc)
        assert set(roles) == set(CanonicalRole)
        assert all(s.confidence == 1.0 for s in roles.values())
        assert "edge devices is hard" in roles[CanonicalRole.CONTEXT].content

    def test_no_headings_returns_single_chunk(self):
        chunks = split_sections("just a plain paragraph without headings.")
        assert chunks == [("", "just a plain paragraph without headings.")]


class TestOllamaStructured:
    @respx.mock
    def test_valid_structured_output(self):
        expected = {
            "has_code_repo": True,
            "code_repo_url": "https://github.com/example/edge-transformers",
            "dataset_specification": "10,000 samples",
            "evaluated_benchmarks": ["GLUE"],
            "declared_limitations": None,
        }
        route = respx.post(f"{OLLAMA}/api/chat").mock(
            return_value=httpx.Response(200, json=ollama_response(expected))
        )
        client = OllamaClient(base_url=OLLAMA)
        result = evaluate_document(make_doc(), client)
        assert isinstance(result, TechnicalMetadata)
        assert result.code_repo_url == expected["code_repo_url"]
        # request phải mang json schema + temperature 0 (structured output tất định)
        sent = json.loads(route.calls[0].request.content)
        assert sent["format"] == TechnicalMetadata.model_json_schema()
        assert sent["options"]["temperature"] == 0

    @respx.mock
    def test_schema_violation_is_permanent_error(self):
        respx.post(f"{OLLAMA}/api/chat").mock(
            return_value=httpx.Response(
                200, json=ollama_response({"has_code_repo": "not-a-bool!!", "extra": 1})
            )
        )
        with pytest.raises(SchemaValidationError):
            evaluate_document(make_doc(), OllamaClient(base_url=OLLAMA))

    def test_empty_context_skips_llm(self):
        # không abstract, không sections -> trả metadata rỗng, không gọi mạng
        result = evaluate_document(make_doc(abstract=None), OllamaClient(base_url=OLLAMA))
        assert result == TechnicalMetadata(has_code_repo=False)


class TestStructuralParser:
    @respx.mock
    def test_full_parse_flow(self):
        tech = {
            "has_code_repo": True, "code_repo_url": "https://github.com/x",
            "dataset_specification": None, "evaluated_benchmarks": ["GLUE", "SQuAD"],
            "declared_limitations": "limited to encoder-only models",
        }
        critique = {"questions": [
            "Why does the evaluation exclude decoder architectures?",
            "How was the 3.2x speedup measured across heterogeneous devices?",
        ]}
        responses = iter([tech, critique])
        respx.post(f"{OLLAMA}/api/chat").mock(
            side_effect=lambda req: httpx.Response(200, json=ollama_response(next(responses)))
        )

        doc = StructuralParser(OllamaClient(base_url=OLLAMA)).parse(
            make_doc(full_text=FULL_TEXT)
        )
        assert doc.sections is not None
        assert doc.sections.doc_type == "A"  # nguồn ieee -> IMRAD
        assert doc.tech_meta.evaluated_benchmarks == ["GLUE", "SQuAD"]
        assert len(doc.critique_questions) == 2
        assert all(q.labels == ["[CONFIRMED]", "[INFERRED]", "[UNKNOWN]"]
                   for q in doc.critique_questions)
