"""Tests for tools/protocol_build.py (PICO Review Protocol)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from tools.protocol_build import (
    PicoConcept,
    ReviewProtocol,
    compile_queries,
    draft_protocol_llm,
    make_concept_expr,
    make_skeleton,
    make_slug,
    render_pico_query,
)

OLLAMA = "http://localhost:11434"


class TestSlug:
    def test_make_slug_basic(self):
        assert make_slug("Retrieval Augmented Generation") == "retrieval-augmented-generation"

    def test_make_slug_vietnamese(self):
        assert make_slug("Tìm kiếm thông tin y sinh") == "tim-kiem-thong-tin-y-sinh"


class TestConceptExpr:
    def test_single_concept(self):
        concept = PicoConcept(concept="Retrieval-Augmented Generation")
        assert make_concept_expr(concept) == '"Retrieval-Augmented Generation"'

    def test_concept_with_synonyms(self):
        concept = PicoConcept(concept="RAG", synonyms=["Retrieval Augmented Generation", "Retrieval-Augmented Generation"])
        assert make_concept_expr(concept) == '("RAG" OR "Retrieval Augmented Generation" OR "Retrieval-Augmented Generation")'


class TestRenderPicoQuery:
    def test_render_with_p_and_i_placeholders(self):
        template = '("{P}") AND ("{I}")'
        p_expr = '"LLM"'
        i_expr = '("RAG" OR "retrieval")'
        # normalized template formatting
        res = render_pico_query(template, p_expr, i_expr)
        assert res == '("LLM") AND (("RAG" OR "retrieval"))'

    def test_render_with_terms_placeholder(self):
        template = '"{terms}"'
        p_expr = '"LLM"'
        i_expr = '"RAG"'
        res = render_pico_query(template, p_expr, i_expr)
        # Should strip the outer quotes of the template when formatting complex boolean expression
        assert res == '"LLM" AND "RAG"'


class TestCompileQueries:
    def test_compile_queries_keeps_p_and_i_only(self):
        protocol = ReviewProtocol(
            topic_vi="chủ đề",
            population=PicoConcept(concept="LLM", synonyms=["large language models"]),
            intervention=PicoConcept(concept="RAG"),
            comparison=PicoConcept(concept="Fine-tuning"),  # C should be ignored in search query
            outcome=PicoConcept(concept="Hallucination"),   # O should be ignored in search query
            exclusion_criteria=[]
        )
        profile = {
            "sources": {
                "ieee": {"templates": ["{terms}"]},
                "arxiv": {"templates": ["{terms}"]}
            }
        }
        queries = compile_queries(protocol, profile, ["ieee", "arxiv"])
        expected_query = '("LLM" OR "large language models") AND "RAG"'
        assert queries["ieee"] == [expected_query]
        assert queries["arxiv"] == [expected_query]


class TestDraftProtocolLLM:
    @respx.mock
    def test_draft_llm_success(self):
        dummy_protocol = {
            "topic_vi": "chủ đề test",
            "population": {"concept": "LLM", "synonyms": ["large language models"], "required": True},
            "intervention": {"concept": "RAG", "synonyms": [], "required": True},
            "languages": ["en"],
            "study_types_excluded": ["editorial"],
            "exclusion_criteria": ["ET1", "ET2"]
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {
                "role": "assistant",
                "content": json.dumps(dummy_protocol)
            }
        }))
        
        protocol = draft_protocol_llm("chủ đề test")
        assert protocol.population.concept == "LLM"
        assert protocol.intervention.concept == "RAG"
        assert protocol.exclusion_criteria == ["ET1", "ET2"]

    @respx.mock
    def test_draft_llm_fallback_when_ollama_down(self):
        respx.get(f"{OLLAMA}/api/tags").mock(side_effect=httpx.ConnectError("down"))
        protocol = draft_protocol_llm("chủ đề offline")
        # should fallback to empty skeleton
        assert "[Điền Population" in protocol.population.concept
        assert protocol.topic_vi == "chủ đề offline"
