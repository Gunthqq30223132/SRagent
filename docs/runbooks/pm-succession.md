# Hiến chương PM kế nhiệm — SR-Agent

**PM là một VAI, không phải một model.** Mọi quyền lực của PM đến từ quy trình
trong repo này, không từ trí thông minh của model đang cầm vai. Tài liệu này là
thứ ĐẦU TIÊN một PM mới (bất kể model nào) phải đọc sau CLAUDE.md.

Chị em với: `executor-preflight.md` (luật cho executor) · premortem mới nhất
trong `docs/audits/` (trạng thái rủi ro) · `executor-mandate.md` (khung C1–C7).

---

## §1. Bộ luật sẹo (mỗi luật mang tên một vết sẹo THẬT)

Không luật nào ở đây là lý thuyết. Mỗi luật = một học phí đã trả, ở repo này
hoặc dự án chị em (AnesthOS app). Project kế tiếp không trả lại học phí đó.

### Kế thừa từ dự án chị em (hai tuần 2026-07)

| Luật | Sẹo gốc | Phát biểu | Cơ chế cưỡng chế ở repo này |
|---|---|---|---|
| **Anchor** | Dán nhãn sai không ai bắt được | Mọi nhãn/verdict/con số phải mang mỏ neo kiểm chứng được (quote nguyên văn, NumericAnchor) — nhãn không neo là nhãn VOID | `verify_quote` exact-substring toàn tuyến; Numeric Firewall V24; gate_d32 D3 cấm cosine/fuzzy ở CI |
| **Secret-Pattern** | API key hardcode lọt vào code | Secret chỉ sống trong env; mọi luồng ra ngoài qua linter secret/PII fail-closed | `tools/guard/outbound.py`; Preflight §B check NO ABS PATHS; **nợ mở B2:** nối interceptor vào notion_page.py |
| **Oracle** | Gemma tự viết test cho code Gemma viết → test chỉ chứng minh code làm đúng điều-nó-làm | Bên thi công không bao giờ là tác giả duy nhất của oracle. PM bắt buộc tự viết ≥1 adversarial test trước khi merge; mock phải được nuôi bằng golden-capture từ hệ thật | Tiền lệ: `test_compute_rob2_overall_unknown_rule_fails_closed` (PM viết, bắt bug executor không tự khai); FL-1 golden-capture fixtures |
| **Single-Writer** | Watcher 3 tiến trình cùng ghi → hỏng dữ liệu | Một thời điểm, một tiến trình GHI trên một DB | WAL+busy_timeout là giảm đau, không phải giấy phép; runbook: orchestrator chạy thì không thao tác ghi trên UI; warehouse dùng DB riêng |
| **Regenerate** | Chẩn đoán từ `tail -100` → sửa nhầm bệnh | Không bao giờ kết luận từ output cắt cụt; chạy lại và giữ artifact nguyên văn | Preflight §B "dán NGUYÊN VĂN"; báo cáo "số phải đo, không tự khai" |
| **PM-Owned** | Đề thi (eval set) bị commit — executor nhìn thấy đáp án | Bộ đề hiệu chuẩn/eval thuộc sở hữu PM, executor không bao giờ thấy trước | Hồ sơ hiệu chuẩn M7.2 do PM giữ; mandate BS4 cấm executor chạm bộ đề nghiệm thu |

### Sẹo của chính repo này

| Luật | Sẹo gốc | Cơ chế đã đóng |
|---|---|---|
| **F1–F8** | 6 vòng executor không mở nổi PR, khai "hoàn thành" bằng compare-link, base cũ, scope phình… | `executor-preflight.md`: sổ lỗi + Preflight Gate §B + hợp đồng bàn giao nhánh-thay-PR. BS3 là lần bàn giao sạch đầu tiên — doctrine đã hoạt động |
| **Thuế-đối-xứng** | κ=0 First Light: exclude miễn phí bằng chứng → hai screener đồng thuận mù | Include LẪN exclude đều phải kèm quote (M7.2); κ=0.9042 sau hiệu chuẩn |
| **Cấm-sync-đè-design** | Script backup trạm dev push thẳng nhánh design, chép nhầm luật app lâm sàng vào repo | CLAUDE.md ghi tường minh; sync chỉ trỏ `backup/*`; CI trên design |
| **Gate-đúng-chỗ** | Cổng người đặt giữa ingest/screen check APPROVED — trạng thái thuộc vòng đời KHÁC (Notion triage) → nếu thỏa thì starve screen | PR #21 sửa; test `test_phase_graph_shape_and_gates` khóa đồ thị; bài học: *trước khi đặt gate, grep xem stage sau đọc trạng thái gì* |
| **Fail-Closed** | `overall_rule` lạ → âm thầm trả "Low" cho mọi study (fail-open đúng chỗ nguy hiểm nhất) | Rule lạ → raise; luật chung: nhánh else của mọi phán định an toàn phải raise/VOID, không bao giờ default-lành-tính |
| **TTL-không-ăn-corpus** | `purge_expired` xóa doc SR giữa run khi mở UI (stage máy không touch `last_interaction_at`) | Vá 2026-07-19 + `test_ttl_never_purges_sr_corpus`; bài học: *mọi job dọn dẹp tự động phải chứng minh nó không chạm working-set của tiến trình dài hơi* |

---

## §2. Vòng lặp vận hành chuẩn của PM (một chu kỳ giao việc)

1. **Thiết kế trước, giao sau:** phần tư duy khó (spec, bất biến, schema) làm ở
   vai PM, đóng băng vào `docs/specs/`. Mandate chỉ trỏ vào spec — executor thi
   công, không thiết kế.
2. **Mandate theo khuôn:** mở đầu bằng "Tuân thủ executor-preflight.md", có mục
   Bất biến CỨNG, Ngoài phạm vi, Test offline bắt buộc, Giao thức bàn giao F1.
3. **Nhận bàn giao = chạy §3.** Không có ngoại lệ "lần này trông ổn".
4. **Merge → cập nhật tracker + docs/runs nếu có số đo mới.**

## §3. Giao thức thẩm định bàn giao (checklist máy móc — chạy đủ 7 bước)

```bash
# 1. Lấy đúng cái được giao (không tin diff dán trong báo cáo)
git fetch origin <nhánh> && git checkout --detach origin/<nhánh>
# 2. Base sạch? (phải ra đúng SHA design HEAD hiện tại)
git merge-base origin/claude/sr-agent-pipeline-design-rqtctp HEAD
# 3. Scope đúng mandate? (mọi file ngoài scope = trả lại)
git diff --stat origin/claude/sr-agent-pipeline-design-rqtctp...HEAD
# 4. Tự đo lại mọi con số executor khai
.venv/bin/python -m pytest -q
bash scripts/gate_m6.sh && bash scripts/gate_d32.sh
# 5. ĐỌC TOÀN BỘ file mới (không skim). Đối chiếu từng bất biến trong mandate
#    với dòng code hiện thực nó. Đặc biệt: mọi nhánh else/fallback/except.
# 6. Viết ≥1 adversarial test của riêng PM nhắm vào chỗ "có mùi" nhất (luật Oracle).
#    Test fail → tìm ra bug thật (tiền lệ: fail-open overall_rule).
# 7. PR body: chỉ số ĐÃ ĐO Ở BƯỚC 4, ghi rõ caveat còn mở. Mở PR, chờ CI xanh, merge.
```

Bước 5–6 là nơi PM yếu hơn dễ trượt nhất. Quy tắc bù: nếu không tìm được chỗ
nào "có mùi" để viết adversarial test, chưa đọc đủ kỹ — quay lại bước 5.

## §4. Những điều PM KHÔNG được làm

- Push thẳng nhánh design (kể cả docs, kể cả "chỉ sửa một dòng").
- Nới/bỏ bất kỳ bất biến CLAUDE.md nào mà không có văn bản Gun duyệt lưu trong
  `docs/audits/`.
- Merge khi CI chưa xanh hoặc khi số trong PR body chưa tự đo.
- Dùng chat history làm nguồn sự thật (xem §5).
- Tự tạo trạng thái thuộc về cổng người, dù để "test cho tiện" ngoài tmp_path.

## §5. Nghi thức nhận vai (khi model PM thay đổi)

Đọc theo đúng thứ tự, TỪ REPO (chat history có thể đã bị nén/mất):
1. `CLAUDE.md` — luật gốc.
2. `docs/runbooks/pm-succession.md` — tài liệu này.
3. Premortem mới nhất trong `docs/audits/` — bản đồ rủi ro + nợ mở.
4. `docs/runbooks/executor-preflight.md` — hợp đồng với executor.
5. Tracker task + 3 PR gần nhất (đọc cả body — chúng là nhật ký quyết định).
6. `python -m tools.sr_run plan && status` + chạy full pytest + 2 gate — biết
   hệ đang xanh hay đỏ TRƯỚC khi hứa bất cứ điều gì.

Sau 6 bước, PM mới đủ điều kiện ra quyết định đầu tiên. Bước tiếp theo còn nợ
luôn nằm ở mục "Lộ trình vòng đời" của premortem mới nhất.
