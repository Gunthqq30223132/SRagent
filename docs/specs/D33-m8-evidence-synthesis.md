# D33 / M8 — Evidence Synthesis Layer: đa nguồn thư mục, trích xuất song thẩm, tổng hợp có neo

> **Bối cảnh ra đời**: chủ dự án xác nhận hướng ứng dụng thật là tổng hợp bằng chứng
> y văn (đích: hỗ trợ nghiên cứu gây mê — "AnesthOS" là TÊN ỨNG DỤNG HẠ NGUỒN, không
> phải tên tầng code). Chuẩn tham chiếu: PRISMA 2020 + Cochrane RAISE (AI có trách
> nhiệm trong tổng hợp bằng chứng: con người chịu trách nhiệm cuối, minh bạch, kiểm
> chứng được — trùng khớp các nguyên tắc M6/D30 đã xây).

## §0 — QUYẾT ĐỊNH D30-S1 (ghi nhận chính thức)

- **D30-S1 = MỞ** (quyết bởi chủ dự án, 2026-07-11): **y văn đã xuất bản** (metadata
  thư mục + toàn văn bài báo từ PubMed/Embase/Europe PMC/arXiv/IEEE) vào phạm vi xử lý.
- **KHÔNG ĐỔI**: dữ liệu bệnh nhân/PII tuyệt đối ngoài phạm vi — Outbound Interceptor
  (NĐ 13/2023/NĐ-CP) giữ nguyên trên mọi luồng rời máy.
- **KHÔNG ĐỔI**: đầu ra của hệ là **tư liệu nghiên cứu cho người duyệt** (bảng bằng
  chứng, PRISMA, tổng hợp có trích dẫn) — KHÔNG phải khuyến nghị lâm sàng cho người
  bệnh; mọi kết quả qua cổng người duyệt (WIP-5, UI) như từ M2 tới nay.
- **KHÔNG ĐỔI**: core topic-blind — ngữ nghĩa gây mê/lâm sàng sống trong PROTOCOL
  (JSON) và dữ liệu, không bao giờ vào code `sr_agent/`.

## §1 — Kiến trúc M8 (Open/Closed: chỉ THÊM adapter, core 0 dòng)

```
                       ┌──────────── M8 EVIDENCE LAYER (tools/evidence/) ────────────┐
.ris/.bib exports ──►  reference_parse (RIS+BibTeX → RefRecord, tất định, local)     │
(PubMed/Embase/         │                                                            │
 EuropePMC/IEEE/arXiv)  ▼                                                            │
                       dedup_multi (tầng 1 exact external-ID → tầng 2 fuzzy title    │
                        rapidfuzz [dep sẵn có] → tầng 3 authority tier) + bench F1   │
Semantic Scholar ──►   snowball (BFS chặn: depth/cap/saturation — không vòng vô hạn) │
                        │                                                            │
                        ▼                    2 agent độc lập (model A ≠ B, temp 0)   │
                       extract_stats (form theo PROTOCOL; claim = giá trị BYTE-EXACT │
                        + quote verbatim qua verify_quote; lệch số → arbiter ẩn danh │
                        → không phân xử được → HUMAN_REVIEW, không bao giờ đoán)     │
                       └──────────────────────────────────────────────────────────────┘
                                │ RefRecord/ConsensusOutcome (Pydantic)
                                ▼
             CHUỖI CŨ KHÔNG ĐỔI: staging → screening kép M6 → eligibility M7.3
             → SynthesisProvider D31.2 (outline-first per-section + firewall V24)
             → prisma_report (audit trail REASON_CODE + quote — đã có từ M6/M7.3)
```

Bố cục thư mục: `tools/evidence/{schemas,reference_parse,dedup_multi,snowball,extract_stats}.py`
+ `tests/test_evidence_m8.py`. Không file nào ngoài đó (trừ spec này).

## §2 — Hiệu chỉnh trung thực các tiêu chí nghiệm thu

| Đề bài | Hiệu chỉnh của kiến trúc sư | Lý do |
|---|---|---|
| Result A: "F1 ≥ 99.5% trên 10.000+ bản ghi" | Giao **harness đo F1** (`benchmark_f1`) + corpus tổng hợp có nhãn; con số thật đo TRÊN MÁY THẬT và báo cáo — không tự khai trước | Số chưa đo = số bịa; đúng luật dự án |
| Result A: "nguồn chọn theo chủ đề" | Chọn nguồn = việc của NGƯỜI khi export .ris/.bib; hệ nhận file, không tự quyết nguồn | Giữ human-gate + provenance |
| Result B: "verification loop zero-trust" | Quote verbatim (verify_quote) + so số byte-exact + arbiter ẩn danh + HUMAN_REVIEW — KHÔNG có vòng "LLM tự sửa đến khi khớp" | Verdict void ≠ verdict fixed (bất biến từ M6) |
| Result C (outline-first + neo `[Study_ID:Para:Quote]`) | ĐÃ CÓ NỀN: D31.2 SynthesisProvider + firewall; phần neo per-section là **M8.3** (spec riêng sau khi A+B chạy thật) | Không nhồi 1 PR |
| Result D (saturation + prisma_audit_trail) | Luật dừng tất định đã đặt trong snowball (M8.1); audit trail = mở rộng prisma_report — **M8.4** | Như trên |

## §3 — Hợp đồng dữ liệu & prompt (Result A + B, giao trong PR này)

- `RefRecord`: `external_ids{doi,pmid,arxiv,s2…}` + `canonical_uid()` ưu tiên doi→pmid→arxiv→s2→title-hash; provenance = file+index.
- Dedup: quan hệ trùng qua union-find trên external-ID chung; fuzzy title cutoff 93
  (đồng bộ D34); tier nguồn khai báo được (`pubmed/embase/ieee=1, europepmc/arxiv=2, s2=3`).
- Snowball: `SnowballConfig{max_depth=1, max_refs_per_paper=50, max_total=200,
  min_new_unique_rate=0.1}` — chạm bất kỳ trần nào ⇒ dừng + `stopped_reason`;
  URL API qua `assert_sanitized` trước khi gửi.
- Extraction form theo protocol (Elicit-style): `FieldSpec{name, description, kind
  numeric|text, required}`; form MẶC ĐỊNH có sample_size/mean/sd/p_value nhưng bảng
  thật do protocol định nghĩa — code không biết "gây mê" là gì.
- Prompt extractor (system): vai người trích xuất SR; CHỈ chép NGUYÊN VĂN; số sao
  từng ký tự; thiếu = null; cấm suy ra/lấp chỗ trống; JSON đúng schema. Prompt arbiter:
  nhận 2 giá trị ẨN DANH + 2 quote, chọn "a"/"b"/"neither" kèm quote — "neither" =
  đẩy người. (Toàn văn prompt nằm trong `extract_stats.py` — code là nguồn sự thật.)

## §4 — Roadmap M8

| Phase | Nội dung | Giao |
|---|---|---|
| **M8.1 (PR này)** | Result A + B: parse/dedup/bench + snowball + extract song thẩm | Fable ✅ |
| M8.2 | Chạy bench 10k thật trên Mac + First Light resume | Antygravity |
| M8.3 | Result C: outline-first + neo `[Study_ID:Para:Quote]` trên SynthesisProvider | spec sau M8.2 |
| M8.4 | Result D: prisma_audit_trail.md hợp nhất + saturation cho search chủ đề | spec sau M8.2 |
