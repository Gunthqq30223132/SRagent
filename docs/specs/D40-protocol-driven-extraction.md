# D40 — Protocol-driven Extraction: trường trích xuất khai trong protocol, không hardcode

**Trạng thái:** thiết kế đóng băng 2026-07-19 (PM Fable 5). Thi công theo mandate
riêng; PM thẩm định theo `pm-succession.md` §3. **Không thiết kế lại.**
**Giải quyết:** audit kiến trúc 2026-07-19 phát hiện A5 — taxonomy trích xuất CS
(`has_code_repo/dataset_spec/baselines/metrics`) hardcode trong
`tools/evidence_extract.py`, chặn cứng pivot sang y văn (cần PICO: agent, dose,
comparator, outcome). Vi phạm tinh thần bất biến CLAUDE.md #3: ngữ nghĩa miền
phải nằm trong PROTOCOL JSON, không trong code.

## §0. Nguyên tắc

1. **Protocol là chủ schema**: bộ trường trích xuất, mô tả, và gợi ý giá trị nằm
   trọn trong protocol JSON. Tool chỉ dựng schema động + prompt từ đó — đổi đề
   tài SR là đổi protocol, KHÔNG đổi code.
2. **Mọi trường giữ nguyên khuôn EvidencedField** (`value` + `quote` verbatim +
   `section`): thuế bằng chứng không đổi, verify_quote exact-match không đổi.
3. **Backward-compat tuyệt đối**: protocol không có `extraction_fields` ⇒ dùng
   bộ 4 trường CS hiện tại (đóng băng thành hằng `LEGACY_EXTRACTION_FIELDS`,
   đánh dấu legacy trong docstring). Mọi test cũ chạy nguyên.

## §1. Schema protocol (khối mới, tùy chọn)

```json
"extraction_fields": [
  {"id": "intervention_dose",
   "description_en": "The dose/concentration of the intervention agent, verbatim with units, else null.",
   "value_hint": "verbatim number + unit"},
  {"id": "primary_outcome",
   "description_en": "The primary outcome measure as stated by the authors, else null."},
  ...
]
```

- `id`: snake_case, khớp `^[a-z][a-z0-9_]{2,40}$` — thành tên field pydantic
  và giá trị cột `field` trong bảng `extraction` (schema DB không đổi).
- `description_en`: dòng mô tả đưa vào system prompt (đánh số tự động).
- `value_hint` (tùy chọn): phụ chú thêm sau mô tả trong prompt.
- Validate trong `ReviewProtocol` (tools/protocol_build.py): id trùng nhau ⇒
  lỗi nạp protocol (fail-closed lúc load, không đợi lúc chạy).

## §2. Thay đổi trong `tools/evidence_extract.py`

1. **Schema động**: `pydantic.create_model("EvidencedExtraction", **{f.id:
   (EvidencedField, ...) for f in fields})` — mọi trường bắt buộc, cùng khuôn
   `EvidencedField` hiện có. Không eval/exec, không template string sinh code.
2. **Prompt động**: phần liệt kê field trong system prompt render từ
   `extraction_fields` (số thứ tự + id + description_en + value_hint); phần luật
   (verbatim quote, section, JSON schema) giữ NGUYÊN VĂN như hiện tại — luật
   chép quote là tài sản đã hiệu chuẩn, không viết lại.
3. **Value-anchor consistency (hợp đồng mới, áp cho MỌI trường kể cả legacy):**
   sau khi `verify_quote` pass, mọi chữ số xuất hiện trong `value` PHẢI xuất
   hiện trong `quote` (so trên tập số bóc bằng `extract_anchors` của
   `tools/guard/firewall.py` — chỉ IMPORT, guard zero-touch). Lệch ⇒
   `verified=0` + event `EXTRACT_VALUE_MISMATCH` (detail = field id, KHÔNG chép
   value/quote vào event). Chặn tất định ca "quote đúng 50 mg nhưng value ghi
   500 mg" — với y văn đây là failure mode chết người, không phải cosmetic.
   `value` không chứa chữ số nào ⇒ check bỏ qua (trường định tính).
4. Tiền điều kiện ELIG_INCLUDED + context từ `build_full_text_str` (sau khi
   MED-READY vá A4) giữ nguyên — D40 không đụng khâu chọn doc.

## §3. Test offline bắt buộc (mở rộng `tests/test_extraction.py`)

(a) protocol có extraction_fields ⇒ schema động đúng tên field, thiếu field
trong output LLM (mock) ⇒ SchemaValidationError; (b) không có extraction_fields
⇒ 4 trường legacy, test cũ nguyên; (c) id trùng ⇒ lỗi nạp protocol; (d)
value-anchor: value "500 mg" + quote chỉ có "50 mg" ⇒ verified=0 + event đúng
field; value khớp số trong quote ⇒ verified=1; value định tính không số ⇒ check
bỏ qua; (e) event không chứa value/quote. Ratio assert/test ≥ 2.

## §4. Ngoài phạm vi

Trường lặp theo outcome (một bài nhiều outcome — v2, cần bảng con, đợi nhu cầu
thật từ FL-4) · quy đổi đơn vị (KHÔNG BAO GIỜ — byte-exact only, quy đổi là
việc của người đọc bảng) · dịch value sang tiếng Việt (value là dữ liệu, giữ
nguyên ngôn ngữ gốc).
