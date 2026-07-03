"""Benchmark thủ công: so sánh model Ollama trên tác vụ trích TechnicalMetadata.

Chạy trên máy thật (cần Ollama đang chạy + đã pull model):
    .venv/bin/python tests/bench_parser.py qwen2.5:7b-instruct gemma3:4b

Đo: thời gian, tỉ lệ pass Pydantic schema, kết quả trích so với ground truth
của fixture IEEE (bài 38111222 có repo/dataset/benchmark/limitation tường minh).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from sr_agent.ingest.ieee import IEEEXploreFetcher
from sr_agent.parser.evaluator import evaluate_document
from sr_agent.parser.ollama_client import OllamaClient

RUNS_PER_MODEL = 3

EXPECTED = {
    "has_code_repo": True,
    "code_repo_url": "https://github.com/example/edge-transformers",
    "dataset_hint": "10,000",
    "benchmark_hints": {"GLUE", "SQuAD"},
}


def main(models: list[str]) -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "ieee_search.json").read_text()
    )
    doc = IEEEXploreFetcher(api_key="offline").parse_search_json(fixture)[0]

    for model in models:
        client = OllamaClient(model=model)
        if not client.is_available():
            print(f"[SKIP] Ollama không phản hồi — bỏ qua {model}")
            continue
        print(f"\n=== {model} (x{RUNS_PER_MODEL}) ===")
        ok, correct, elapsed = 0, 0, 0.0
        for i in range(RUNS_PER_MODEL):
            t0 = time.perf_counter()
            try:
                meta = evaluate_document(doc, client)
                dt = time.perf_counter() - t0
                elapsed += dt
                ok += 1
                hits = [
                    meta.has_code_repo == EXPECTED["has_code_repo"],
                    meta.code_repo_url == EXPECTED["code_repo_url"],
                    bool(meta.dataset_specification)
                    and EXPECTED["dataset_hint"] in meta.dataset_specification,
                    EXPECTED["benchmark_hints"] <= set(meta.evaluated_benchmarks),
                    meta.declared_limitations is not None,
                ]
                correct += sum(hits)
                print(f"  run {i+1}: {dt:.1f}s, đúng {sum(hits)}/5 trường")
            except Exception as exc:
                print(f"  run {i+1}: FAIL — {type(exc).__name__}: {exc}")
        if ok:
            print(f"  -> schema pass {ok}/{RUNS_PER_MODEL}, "
                  f"độ đúng {correct}/{ok * 5}, trung bình {elapsed / ok:.1f}s/lần")


if __name__ == "__main__":
    main(sys.argv[1:] or ["qwen2.5:7b-instruct", "gemma3:4b"])
