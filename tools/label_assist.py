"""Trợ lý dán nhãn vàng cho hiệu chuẩn miền y khoa (M7.2-MED).

Nguyên tắc DUY NHẤT chi phối file này:

    Máy được phép đưa BẰNG CHỨNG. Máy không được đưa PHÁN QUYẾT.

Nhãn vàng tồn tại để ĐO xem máy có đáng tin không. Nếu máy sinh ra nhãn vàng thì
phép đo trở thành vòng lặp tự chứng: ta đo screener A bằng nhãn do chính A tạo,
đồng thuận ≈ 100%, κ ra ~0.9 và KHÔNG mang thông tin nào. Vì vậy:

- Đường `label` KHÔNG gọi LLM. Không import client nào. Bằng chứng hiển thị là
  câu NGUYÊN VĂN bóc từ abstract bằng luật tất định (substring exact, không
  cosine/fuzzy — bất biến CLAUDE.md #2), nên không có gì để bịa.
- Không bao giờ hiển thị verdict của máy trong lúc người đang phán. Trích câu
  chứa liều/kết cục/thiết kế thì tiết kiệm thời gian đọc mà KHÔNG neo phán định;
  hiện "INCLUDE/EXCLUDE" thì neo cứng — người sẽ gật theo.
- Verdict máy chỉ được đọc ở lệnh `score`, SAU khi nhãn người đã đóng băng.

Ngữ nghĩa miền nằm trong PROTOCOL (PICO + unit_lexicon), không trong code —
`DESIGN_TERMS` là từ vựng phương pháp luận SR (dùng chung mọi đề tài), không
phải từ vựng bệnh học.

Dùng:
    python -m tools.label_assist label --input abstracts.csv --protocol p.json \\
        --gold data/m72med-gold.csv
    python -m tools.label_assist score --gold data/m72med-gold.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sr_agent.monitor.health import compute_cohen_kappa  # noqa: E402
from sr_agent.store.staging import StagingStore  # noqa: E402

GOLD_COLUMNS = ["pmid", "uid", "is_decoy", "label", "reason", "note", "labeled_at"]
DEFAULT_UID_PREFIX = "europepmc:MED:"
CRITERIA_PATH = ROOT / "tools" / "criteria" / "default.json"

INCLUDE = "INCLUDE"
EXCLUDE = "EXCLUDE"

# Từ vựng PHƯƠNG PHÁP LUẬN SR — dùng chung mọi đề tài, không mang ngữ nghĩa bệnh học.
# Đây là lý do nó được phép nằm trong code: đổi đề tài SR không cần sửa danh sách này.
DESIGN_TERMS = [
    "randomi",          # randomized / randomised / randomisation
    "double-blind", "single-blind", "placebo", "crossover", "cross-over",
    "cohort", "case-control", "case series", "case report",
    "prospective", "retrospective", "observational",
    "systematic review", "meta-analys", "editorial", "letter to the editor",
    "protocol", "pilot study", "feasibility",
]

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Điểm cho từng loại tín hiệu. Cố ý thô: mục tiêu là ĐẨY câu đáng đọc lên đầu,
# không phải xếp hạng tinh vi — người vẫn đọc và quyết.
W_NUMBER_WITH_UNIT = 4
W_NUMBER = 2
W_PICO_GROUP = 3
W_DESIGN = 3


# --- Thu thập từ khóa từ protocol (ngữ nghĩa miền ở protocol, không ở code) ----------


def collect_terms(protocol: Any) -> dict[str, list[str]]:
    """Gom từ khóa theo NHÓM PICO, giữ nhóm để chấm điểm theo số nhóm khớp."""
    groups: dict[str, list[str]] = {}
    for name in ("population", "intervention", "comparison", "outcome"):
        concept = getattr(protocol, name, None)
        if concept is None:
            continue
        terms = [concept.concept, *getattr(concept, "synonyms", [])]
        groups[name] = [t for t in terms if t]
    return groups


def _units(protocol: Any) -> list[str]:
    return list(getattr(protocol, "unit_lexicon", None) or [])


def _contains(haystack_cf: str, needle: str) -> bool:
    """Substring exact sau casefold. KHÔNG fuzzy, KHÔNG cosine (bất biến #2)."""
    return needle.casefold() in haystack_cf


# --- Chọn bằng chứng (tất định) -------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def has_number_with_unit(sentence: str, units: list[str]) -> bool:
    """Câu mang <số> <đơn_vị> — liều thuốc, độ sâu mê, tỉ lệ kết cục."""
    return any(
        re.search(rf"{re.escape(n)}\s*{re.escape(u)}(?!\w)", sentence, re.IGNORECASE)
        for n in NUMBER_RE.findall(sentence)
        for u in units
    )


def score_sentence(sentence: str, groups: dict[str, list[str]], units: list[str]) -> int:
    cf = sentence.casefold()
    score = 0

    if NUMBER_RE.search(sentence):
        score += (
            W_NUMBER_WITH_UNIT if has_number_with_unit(sentence, units) else W_NUMBER
        )

    for terms in groups.values():
        if any(_contains(cf, t) for t in terms):
            score += W_PICO_GROUP

    if any(_contains(cf, d) for d in DESIGN_TERMS):
        score += W_DESIGN

    return score


def select_evidence(
    abstract: str, protocol: Any, k: int = 3
) -> list[str]:
    """Trả về ≤k câu NGUYÊN VĂN, giữ đúng thứ tự xuất hiện trong abstract.

    Mọi câu trả về là substring của abstract — không diễn giải, không tóm tắt,
    nên không có đường nào để bịa nội dung.
    """
    sentences = split_sentences(abstract)
    if not sentences:
        return []
    groups = collect_terms(protocol)
    units = _units(protocol)

    scored = [
        (score_sentence(s, groups, units), idx, s) for idx, s in enumerate(sentences)
    ]
    scored = [t for t in scored if t[0] > 0]
    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen = scored[:k]

    # Bảo đảm câu mang <số> <đơn_vị>: với SR lâm sàng, câu chứa liều/tỉ lệ kết cục
    # là loại thông tin KHÁC HẲN về bản chất, không phải "thêm một tín hiệu". Nếu
    # xếp hạng thuần điểm đánh rớt nó (câu mở đầu nhiều từ PICO có thể ăn điểm cao
    # hơn câu liều), ép nó vào chỗ của câu thấp điểm nhất.
    if k > 0 and units and not any(has_number_with_unit(s, units) for _, _, s in chosen):
        dose = next((t for t in scored if has_number_with_unit(t[2], units)), None)
        if dose is not None:
            chosen = chosen[: k - 1] + [dose]

    return [s for _, _, s in sorted(chosen, key=lambda t: t[1])]


def highlight(sentence: str, protocol: Any, color: bool = True) -> str:
    """Tô đậm số, đơn vị, từ PICO và từ thiết kế nghiên cứu."""
    if not color:
        return sentence
    needles: list[str] = []
    for terms in collect_terms(protocol).values():
        needles.extend(terms)
    needles.extend(_units(protocol))
    needles.extend(DESIGN_TERMS)

    out = sentence
    spans: list[tuple[int, int]] = []
    for m in NUMBER_RE.finditer(sentence):
        spans.append(m.span())
    for needle in sorted(set(n for n in needles if n), key=len, reverse=True):
        for m in re.finditer(re.escape(needle), sentence, re.IGNORECASE):
            spans.append(m.span())

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    for start, end in reversed(merged):
        out = out[:start] + "\033[1;33m" + out[start:end] + "\033[0m" + out[end:]
    return out


# --- Đọc/ghi file ---------------------------------------------------------------------


def load_input(path: Path) -> list[dict[str, Any]]:
    """Nhận CSV hoặc JSON; bắt buộc có `pmid` và `abstract`."""
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        pmid = str(r.get("pmid", "")).strip()
        if not pmid:
            raise ValueError(f"Dòng thiếu cột 'pmid': {r}")
        out.append(
            {
                "pmid": pmid,
                "title": (r.get("title") or "").strip(),
                "abstract": (r.get("abstract") or "").strip(),
                "is_decoy": str(r.get("is_decoy", "0")).strip() or "0",
            }
        )
    return out


def read_gold(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["pmid"]: r for r in csv.DictReader(f)}


def append_gold(path: Path, row: dict[str, str]) -> None:
    """Ghi NGAY sau mỗi nhãn — 40 phút công sức không được mất vì một cú Ctrl-C."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GOLD_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def load_criteria() -> dict[str, dict[str, str]]:
    return json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))


# --- Lệnh `label` ---------------------------------------------------------------------


def _render_item(
    item: dict[str, Any], protocol: Any, color: bool, full: bool, k: int = 3
) -> str:
    lines = [
        "",
        f"\033[1mPMID {item['pmid']}\033[0m" if color else f"PMID {item['pmid']}",
        item["title"] or "(không có tiêu đề)",
        "",
    ]
    if full:
        lines += ["Toàn văn abstract:", item["abstract"], ""]
    else:
        evidence = select_evidence(item["abstract"], protocol, k=k)
        if evidence:
            lines.append("Bằng chứng (trích nguyên văn, không phải tóm tắt):")
            for i, sent in enumerate(evidence, 1):
                lines.append(f"  {i}. {highlight(sent, protocol, color)}")
        else:
            lines.append(
                "  (không câu nào khớp từ khóa protocol — bấm [f] để đọc toàn văn)"
            )
        lines.append("")
    return "\n".join(lines)


def _prompt_reason(criteria: dict[str, dict[str, str]], allowed: list[str]) -> str:
    codes = allowed or sorted(criteria)
    print("\n  Mã lý do loại:")
    for code in codes:
        meta = criteria.get(code, {})
        print(f"    {code:<5} {meta.get('label_vi', '')}")
    while True:
        raw = input("  Mã (Enter = bỏ trống): ").strip().upper()
        if not raw or raw in criteria:
            return raw
        print(f"  ✗ '{raw}' không có trong danh mục.")


def cmd_label(args: argparse.Namespace) -> int:
    from tools.protocol_build import ReviewProtocol

    protocol = ReviewProtocol.model_validate_json(
        args.protocol.read_text(encoding="utf-8")
    )
    criteria = load_criteria()
    items = load_input(args.input)
    done = read_gold(args.gold)
    color = sys.stdout.isatty() and not args.no_color

    pending = [it for it in items if it["pmid"] not in done]
    if not pending:
        print(f"✅ Đã dán nhãn đủ {len(items)}/{len(items)} bài. Không còn gì để làm.")
        return 0
    if not sys.stdin.isatty():
        print("❌ Lệnh này cần terminal tương tác.", file=sys.stderr)
        return 2

    print(
        f"\n{len(done)}/{len(items)} đã xong · còn {len(pending)} bài.\n"
        "Phím: [i] nhận  [e] loại  [f] xem toàn văn  [s] để sau  [q] lưu & thoát\n"
        "Lưu ý: máy KHÔNG đưa gợi ý nhận/loại — phán định là của anh."
    )

    skipped = 0
    for idx, item in enumerate(pending, 1):
        full = False
        while True:
            print(f"\n[{idx}/{len(pending)}]", end="")
            print(_render_item(item, protocol, color, full, args.evidence))
            choice = input("> ").strip().lower()

            if choice == "f":
                full = True
                continue
            if choice == "s":
                skipped += 1
                break
            if choice == "q":
                print(f"\n💾 Đã lưu {len(done)} nhãn vào {args.gold}. Chạy lại để tiếp.")
                return 0
            if choice in ("i", "e"):
                label = INCLUDE if choice == "i" else EXCLUDE
                reason = (
                    _prompt_reason(criteria, protocol.exclusion_criteria)
                    if label == EXCLUDE
                    else ""
                )
                note = input("  Ghi chú (Enter = bỏ qua): ").strip()
                append_gold(
                    args.gold,
                    {
                        "pmid": item["pmid"],
                        "uid": f"{args.uid_prefix}{item['pmid']}",
                        "is_decoy": item["is_decoy"],
                        "label": label,
                        "reason": reason,
                        "note": note,
                        "labeled_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                done[item["pmid"]] = {}
                break
            print("  ✗ Phím không hợp lệ.")

    print(f"\n✅ Xong. {len(done)}/{len(items)} đã dán nhãn · {skipped} để sau.")
    print(f"   File: {args.gold}")
    if skipped:
        print("   Chạy lại lệnh này để xử nốt các bài đã bỏ qua.")
    return 0


# --- Lệnh `score` ---------------------------------------------------------------------


def machine_verdicts(store: StagingStore, uids: list[str]) -> dict[str, dict[str, str]]:
    """uid → {agent: verdict}. Lấy phán định MỚI NHẤT của mỗi agent."""
    if not uids:
        return {}
    placeholders = ",".join("?" for _ in uids)
    rows = store.conn.execute(
        f"""SELECT uid, agent, verdict, created_at FROM screening
            WHERE uid IN ({placeholders}) ORDER BY created_at""",
        uids,
    ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["uid"], {})[r["agent"]] = (r["verdict"] or "").strip().lower()
    return out


def include_rate(labels: list[str]) -> float | None:
    valid = [l for l in labels if l in ("include", "exclude")]
    if not valid:
        return None
    return sum(1 for l in valid if l == "include") / len(valid)


def decoy_rejection(pairs: list[tuple[str, str]]) -> tuple[int, int]:
    """(số mồi bị loại đúng, tổng mồi có phán định)."""
    total = len(pairs)
    ok = sum(1 for _, verdict in pairs if verdict == "exclude")
    return ok, total


def acceptance_report(
    gold: dict[str, dict[str, str]],
    machine: dict[str, dict[str, str]],
    kappa_floor: float = 0.75,
) -> str:
    agents = sorted({a for v in machine.values() for a in v})
    human_by_uid = {
        row["uid"]: (row["label"] or "").strip().lower()
        for row in gold.values()
        if row.get("label")
    }

    lines = ["# Nghiệm thu M7.2-MED", ""]
    n_gold = len(human_by_uid)
    n_machine = len(machine)
    lines.append(f"Nhãn người: {n_gold} · doc có phán định máy: {n_machine}")
    lines.append("")

    if not agents:
        lines.append("❌ Chưa có phán định máy nào trong DB — chạy screening trước.")
        return "\n".join(lines)

    # κ giữa hai screener máy (chỉ số cũ) và κ máy↔người (chỉ số THẬT SỰ cần).
    lines.append("| Cặp so | n | κ | Ngưỡng | Kết quả |")
    lines.append("|---|---|---|---|---|")

    if len(agents) >= 2:
        a, b = agents[0], agents[1]
        pairs = [
            (v[a], v[b]) for v in machine.values() if a in v and b in v
        ]
        k = compute_cohen_kappa(pairs)
        lines.append(
            f"| {a} ↔ {b} (máy↔máy) | {len(pairs)} | "
            f"{'—' if k is None else f'{k:.4f}'} | tham khảo | — |"
        )

    for agent in agents:
        pairs = [
            (machine[uid][agent], human_by_uid[uid])
            for uid in human_by_uid
            if uid in machine and agent in machine[uid]
        ]
        k = compute_cohen_kappa(pairs)
        ok = k is not None and k >= kappa_floor
        lines.append(
            f"| **{agent} ↔ người** | {len(pairs)} | "
            f"{'—' if k is None else f'{k:.4f}'} | ≥{kappa_floor} | "
            f"{'ĐẠT' if ok else 'KHÔNG ĐẠT'} |"
        )

    # Include-rate: κ đơn độc MÙ trước đồng thuận thoái hóa (hai screener nhận hết
    # cho κ=0 y hệt hai screener cãi nhau). Bắt buộc đọc kèm.
    lines += ["", "| Rater | Include-rate | Ngưỡng [10%, 90%] |", "|---|---|---|"]
    for agent in agents:
        rate = include_rate([v[agent] for v in machine.values() if agent in v])
        verdict = "—" if rate is None else ("ĐẠT" if 0.10 <= rate <= 0.90 else "KHÔNG ĐẠT")
        lines.append(f"| {agent} | {'—' if rate is None else f'{rate:.1%}'} | {verdict} |")
    hr = include_rate(list(human_by_uid.values()))
    lines.append(f"| người | {'—' if hr is None else f'{hr:.1%}'} | (tham chiếu) |")

    # Mồi: đo "máy có thật sự đọc không, hay gật bừa".
    decoy_uids = {
        row["uid"] for row in gold.values() if str(row.get("is_decoy", "0")) == "1"
    }
    if decoy_uids:
        lines += ["", "| Rater | Mồi bị loại đúng | Ngưỡng ≥80% |", "|---|---|---|"]
        for agent in agents:
            pairs = [
                (uid, machine[uid][agent])
                for uid in decoy_uids
                if uid in machine and agent in machine[uid]
            ]
            ok, total = decoy_rejection(pairs)
            verdict = "—" if not total else ("ĐẠT" if ok / total >= 0.8 else "KHÔNG ĐẠT")
            lines.append(f"| {agent} | {ok}/{total} | {verdict} |")

    return "\n".join(lines)


def cmd_score(args: argparse.Namespace) -> int:
    gold = read_gold(args.gold)
    if not gold:
        print(f"❌ Không đọc được nhãn nào từ {args.gold}.", file=sys.stderr)
        return 2
    store = StagingStore() if args.db is None else StagingStore(args.db)
    uids = [r["uid"] for r in gold.values() if r.get("uid")]
    report = acceptance_report(gold, machine_verdicts(store, uids), args.kappa_floor)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
        print(f"\n📄 {args.out}")
    return 0


# --- CLI ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Trợ lý dán nhãn vàng M7.2-MED (máy đưa bằng chứng, người phán quyết)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_label = sub.add_parser("label", help="dán nhãn tương tác (không gọi LLM)")
    p_label.add_argument("--input", required=True, type=Path)
    p_label.add_argument("--protocol", required=True, type=Path)
    p_label.add_argument("--gold", type=Path, default=Path("data/m72med-gold.csv"))
    p_label.add_argument("--uid-prefix", default=DEFAULT_UID_PREFIX)
    p_label.add_argument("--no-color", action="store_true")
    p_label.add_argument("--evidence", type=int, default=3,
                         help="số câu bằng chứng hiển thị (mặc định 3)")
    p_label.set_defaults(func=cmd_label)

    p_score = sub.add_parser("score", help="so nhãn người (đã đóng băng) với máy")
    p_score.add_argument("--gold", type=Path, default=Path("data/m72med-gold.csv"))
    p_score.add_argument("--db", type=Path, default=None)
    p_score.add_argument("--kappa-floor", type=float, default=0.75)
    p_score.add_argument("--out", type=Path, default=None)
    p_score.set_defaults(func=cmd_score)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
