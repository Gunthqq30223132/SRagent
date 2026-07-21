# D32 — COMPLIANCE-OS: Hệ hỗ trợ cấu hình & compliance hạ tầng zero-hallucination

> **Loại tài liệu**: Master blueprint (spec-only — chưa có code ở phase này). Agent thực thi
> hạ nguồn (Antygravity / agent khác) hiện thực hóa theo roadmap §5, mỗi phase một TS riêng.
>
> **Khung làm việc**: CEVR — Context, Evidence, Verify, Report. **Người dùng đích**: Lead SRE.
> **Quan hệ**: kế thừa trực tiếp D30 (multi-agent + evidence-locked) và D31 (guard modules
> `tools/guard/`, adapter provider, asymmetric fallback). Không thay thế SR-Agent — đây là
> ứng dụng thứ hai xây trên cùng nền tảng kỹ thuật.

## §0 — Phạm vi & bảng đổi tên trung thực

### 0.1 Tuyên bố miền

COMPLIANCE-OS đánh giá **trạng thái hạ tầng trước triển khai** (pre-deployment infrastructure
state), đối chiếu với chuẩn kỹ thuật kinh điển (ISO/IEC, IEEE, RFC) và runbook chuyên gia
địa phương, phát hiện xung khắc cấu hình, và sinh blueprint triển khai đã kiểm chứng.
**Toàn bộ hệ thống nằm trong miền Khoa học Máy tính / vận hành hạ tầng.** Bất biến D30 giữ
nguyên: không có bất kỳ dữ liệu y sinh hoặc lâm sàng nào được xử lý (quyết định D30-S1 vẫn treo
và không bị tài liệu này mở lại).

### 0.2 Bảng đổi tên trung thực

Đề bài gốc chứa một số thuật ngữ lạc miền (mượn từ y khoa). Spec này thay chúng bằng thuật
ngữ hạ tầng thật — **tên gọi trong toàn bộ code và schema phải dùng cột "Thuật ngữ chuẩn"**:

| Thuật ngữ đề bài | Thuật ngữ chuẩn (dùng trong code) | Định nghĩa trong miền hạ tầng |
|---|---|---|
| `evidence_level` 1A/1B | `authority_tier` T1/T2/T3 | T1 = chuẩn normative (ISO/IEC/RFC/IEEE đã phê chuẩn) · T2 = tài liệu vendor chính hãng · T3 = runbook chuyên gia địa phương. Nhất quán với authority tier của dedup D34. |
| "frailty index" | `node_health_index` | Chỉ số tất định tính từ inventory: khoảng cách tới EOL, tuổi kernel, tỉ lệ incident 90 ngày, thời gian từ lần patch cuối. Không có thành phần LLM. |
| "anti-platelet security protocols" | `restricted_change_protocol` | Ràng buộc thay đổi trên node giòn: cửa sổ bảo trì hạn chế, cấm auto-restart dịch vụ nhạy trạng thái, yêu cầu drain thủ công trước rollout. |
| "Non-Device Category" | *(bỏ)* | Không có nghĩa trong SRE — loại khỏi spec. |
| "Never-Events" | `never_event` NE1–NE5 | Giữ tên như một thuật ngữ mượn có định nghĩa riêng tại §4: lớp lỗi mà **một lần xảy ra trong output đã duyệt = sự cố quy trình**, không phải bug thường. |

### 0.3 Nguyên tắc kế thừa từ SR-Agent

- **"AI truy xuất & lọc nhiễu — Con người duyệt & phân tích sâu"**: COMPLIANCE-OS không tự
  triển khai bất cứ thứ gì. Đầu ra cuối là blueprint ở trạng thái `CO_VERIFIED`, chỉ chuyển
  `CO_APPROVED` bởi con người.
- **Tất định ở mọi tầng lọc**: LLM temp 0 + structured output + Pydantic lần cuối; output
  không qua validation = vô hiệu (void), không bao giờ "sửa cho khớp".
- **Fail-closed**: mọi guard chặn khi nghi ngờ; escalate cho người là hành vi mặc định khi
  không chắc chắn — nhất quán ELIG_ESCALATED (M7.3) và tie-breaker D30.

## §1 — Ingestion pipeline: Vector & Relational (CEVR: Evidence)

### 1.1 Docling extraction mapping — bảng compliance → node Markdown nguyên tử

Nối vào roadmap D31.5 (Docling PDF→MD đã có chỗ đứng trong kiến trúc). Quy tắc bóc tách:

1. **Ma trận xung khắc package**: mỗi HÀNG = một node độc lập, tự đứng được:
   `"{pkg_a} {op_a}{ver_a} XUNG KHẮC {pkg_b} {op_b}{ver_b} — điều kiện: {cond} — hành động: {action}"`.
   Header bảng được lặp vào từng node (node không bao giờ cần bảng gốc để hiểu).
2. **Bảng ngưỡng phần cứng/tài nguyên**: mỗi hàng = node `{component, metric, threshold, unit, action_when_exceeded}`.
3. **BẤT BIẾN SỐ HỌC**: mọi con số trong node giữ **byte-exact** so với nguồn — cấm reflow,
   cấm đổi định dạng (`1.2.10` ≠ `1.2.1`, `10 GB` ≠ `10GB` chỉ được chuẩn hóa whitespace theo
   đúng `_normalize` của firewall). Đây là điều kiện tiên quyết để NE1 hoạt động.
4. **Node ID ổn định**: `<doc_id>#<chunk_seq>-<content_sha256_8>` — re-ingest cùng nội dung
   sinh cùng ID; nội dung đổi thì ID đổi và node cũ chuyển `superseded` (chống citation mồ côi NE5).

### 1.2 Metadata schema (payload từng node)

```json
{
  "node_id":        "rfc9110#042-3fa9c1d2",
  "doc_id":         "rfc9110",
  "version":        "2022-06",
  "status":         "draft | active | superseded",
  "domain":         "networking | packaging | storage | security | scheduling",
  "authority_tier": "T1 | T2 | T3",
  "layer":          "L1_canonical | L2_local_runbook",
  "namespace":      "prod | sr_run_<id>",
  "conflict_flag":  null,
  "effective_date": "YYYY-MM-DD",
  "sha256_12":      "..."
}
```

- **Cách ly namespace tuyệt đối**: query production mặc định chỉ đọc `namespace='prod' AND
  status='active'` — enforced tại Orchestrator (§2.2), không phải quy ước. SR run tạm ghi vào
  `sr_run_<id>` có TTL (pattern TTL 72h của staging store), không bao giờ trộn vào prod.
- **Supersede chain**: node mới thay node cũ → node cũ `status='superseded'` + con trỏ
  `superseded_by`; mọi query mặc định lọc superseded, chỉ audit mới đọc lại.
- `conflict_flag` (mặc định null) là cấu trúc khai báo khi node L2 đè node L1 — xem §3-S3 và NE3.

### 1.3 Hybrid search — quyết định kiến trúc & thuật toán

**Quyết định: KHÔNG Qdrant.** Lý do: (a) thêm server process là thêm failure mode và RAM trên
máy 16GB local-first; (b) vi phạm nguyên tắc no-new-runtime-deps; (c) nhu cầu thật (vài nghìn
node compliance) nằm gọn trong SQLite. Thay thế:

- **Lexical (đường bắt buộc)**: **SQLite FTS5** (stdlib, cùng file DB với pattern `SR_AGENT_DB`
  hiện có) — index nguyên văn mọi node.
- **Semantic (tùy chọn, recall-only)**: embedding qua **Ollama embeddings API** (model
  `bge-m3` hoặc tương đương pull về local — không thêm dependency pip), vector lưu BLOB trong
  SQLite, so khớp cosine **chỉ để mở rộng recall — không bao giờ dùng để verify** (bất biến V24).
  Bọc sau adapter kiểu `SynthesisProvider` (D31.3): thiếu model embedding → hệ chạy thuần FTS5,
  suy giảm êm, log rõ.

**Thuật toán truy vấn (chống keyword-miss tuyệt đối cho chuỗi đặc hiệu):**

1. Tokenize query; đối chiếu bảng `known_entities` (mọi package name, metric name, threshold
   xuất hiện trong KB — build tự động **ngay lúc ingest**, không tay).
2. Token khớp known-entity ⇒ **đường FTS5 bắt buộc**, kết quả exact-match được **pin đầu**
   danh sách bất kể điểm vector.
3. Vector search (nếu bật) bổ sung ứng viên recall.
4. Hợp nhất bằng **RRF** (k=60), rồi filter metadata (`namespace`, `status`, `authority_tier`)
   TRƯỚC khi trả về — không lọc sau khi đã đưa vào context LLM.

## §2 — Blueprint 4 agent (CEVR: Verify)

### 2.1 Pydantic schemas (v2 — mọi lệnh LLM: temp 0, structured output, validate lần cuối)

```python
class ComplianceQuery(BaseModel):
    query_id: str
    intent: Literal["migrate", "scale", "residency", "degraded_deploy", "freeform"]
    environment_profile: dict          # inventory node, phiên bản hiện hành
    target_packages: list[str]
    namespace_allowlist: list[str]     # do Orchestrator gán, agent sau không được nới

class ComputedMetric(BaseModel):
    name: str; value: str; unit: str | None
    formula_id: str                    # truy về pure function sinh ra nó

class HardBlock(BaseModel):
    block_id: str; subject: str        # "pkgA==1.2 x pkgB>=3.0"
    reason: str; source_node: str      # node_id trong KB

class LayerAResult(BaseModel):
    query_id: str
    computed: list[ComputedMetric]
    hard_blocks: list[HardBlock]
    hold_flags: list[HoldFlag]         # verdict: HOLD | CONTINUE, kèm source_node
    rollback_required: bool

class AssertionTuple(BaseModel):
    entity: str; attribute: str; value: str
    constraint_source: str             # node_id HOẶC "layer_a:<formula_id>"

class ReconciliationVerdict(BaseModel):
    passed: bool
    violations: list[Violation]
    never_events_triggered: list[str]  # ["NE1", ...]
    rewrite_count: int
    final_state: Literal["CO_VERIFIED", "CO_REJECTED", "CO_ESCALATED"]
```

### 2.2 Orchestrator Agent

- Route theo `intent`; gán `namespace_allowlist` từ **cấu hình tĩnh** (mirror nguyên tắc biên
  `router.py`: ngữ nghĩa dừng ở ngoại vi, core tất định). Query đòi namespace ngoài allowlist ⇒
  từ chối fail-closed, ghi event, không "thử tìm giúp".
- Không gọi LLM. Orchestrator là code thuần.

### 2.3 Execution Agent (Agent-E)

- **THỨ TỰ CỨNG**: Layer A chạy TRƯỚC — pure functions (pattern `rubric.py`: tất định 100%,
  test không cần mock), mục tiêu <50ms — solver ràng buộc version, công thức sizing, tính
  `node_health_index`. Kết quả = `LayerAResult`.
- SAU ĐÓ mới gọi LLM viết prose: context = `LayerAResult` serialize + các node đã retrieve.
  Prompt cấm sinh số mới — nhưng **cấm bằng prompt là KHÔNG ĐỦ** (bài học V24): tầng cưỡng chế
  thật là Agent-R. LLM có thể chạy song song cho các section độc lập của narrative.

### 2.4 Verification Agent (Agent-V)

- Nhiệm vụ: prose → `list[AssertionTuple]`. Nền tảng có sẵn: `extract_anchors`
  (`tools/guard/firewall.py` — complexity/ip/port/percentage/unit/version, span-overlap
  longest-wins). Mở rộng cho D32: pattern `package@version` / `package==version`, cặp cấu hình
  `key=value`, citation token `[node_id]`.
- Agent-V là code tất định (regex + parser), KHÔNG phải LLM chấm LLM — tự chấm là lỗ hổng
  self-attestation đã bịt ở G3/M6.

### 2.5 Reconciliation Agent (Agent-R) — firewall compliance

- Chạy chuỗi checker NE1→NE5 (§4). NE1 dùng nguyên `check_output(strict=True)` hiện có —
  exact regex/string, **cấm cosine cho metric critical** (đã đúng nguyên văn trong firewall).
- **Vòng reject-and-rewrite có trần**: fail ⇒ trả `CO_REJECTED` kèm danh sách violation cho
  Agent-E viết lại (chỉ viết lại prose — `LayerAResult` bất biến trong một run). **Trần 2 lần
  viết lại**; lần thứ 3 vẫn fail ⇒ `CO_ESCALATED` cho người. Không lặp vô hạn, không tự sửa
  số cho khớp (verdict void ≠ verdict fixed).

### 2.6 State machine (tái dùng pattern event-log bảng `events`)

```
CO_DRAFTED ──Agent-V/R──► CO_VERIFIED ──người──► CO_APPROVED
     ▲                        │
     └──── CO_REJECTED ◄──────┤  (viết lại, tối đa 2 vòng)
                              └──► CO_ESCALATED  (hết trần / NE bất kỳ ở mức abort)
```

Mọi transition ghi event kèm evidence (violation list, node_id liên quan) — audit trail giống
`SCREEN_*`/`ELIG_*` hiện hành.

## §3 — Đường thực thi 5 scenario mô phỏng

Khung chung mỗi scenario: *input profile → module Layer A → node KB liên quan → logic xung đột
→ output bắt buộc*. Cả 5 scenario là **fixture test offline** ở D32.4 (pattern respx/FakeFetcher).

### S1 — Emergency legacy migration (di trú khẩn cấp hệ legacy)

- **Input**: manifest dependency hiện tại + target stack; cờ môi trường không ổn định.
- **Layer A**: solver ràng buộc version tất định (resolution theo đồ thị phụ thuộc + pin) —
  KHÔNG có LLM trong khâu giải xung khắc.
- **Logic**: mọi hard block từ ma trận xung khắc PHẢI xuất hiện trong output (NE2); xung khắc
  không giải được ⇒ không bao giờ auto-continue — output là "phương án + block chưa giải"
  ở trạng thái escalate.
- **Output bắt buộc**: `rollback_plan` là trường schema bắt buộc — thiếu = invalid ở tầng
  Pydantic, chưa cần tới firewall. "Khẩn cấp" không nới lỏng bất kỳ gate nào; chỉ đổi thứ tự
  trình bày (block + rollback lên đầu narrative).

### S2 — Multi-cluster scale-up (mở rộng đa cụm)

- **Layer A**: công thức sizing (số replica, CPU/RAM headroom, quorum HA, giới hạn
  anti-affinity) = pure functions, mỗi công thức có `formula_id`.
- **Logic**: LLM chỉ tường thuật và giải thích trade-off; **mọi con số trong prose phải truy
  về `formula_id` hoặc `node_id`** (NE1 + NE4). Tối ưu đa biến chạy trong Layer A (kể cả khi
  chỉ là grid search đơn giản) — không bao giờ nhờ LLM "ước lượng".

### S3 — Localized compliance clampdown (siết compliance địa phương / data-residency)

- **Retrieval**: trả cả L1 (cấu hình cloud toàn cục) lẫn L2 (runbook hạn chế địa phương:
  băng thông, phần cứng, quy định data-residency).
- **Logic xung đột**: L2 được phép đè L1 **chỉ khi** node L2 mang `conflict_flag` khai báo
  (đè node nào, căn cứ pháp lý/vận hành nào, ngày hiệu lực). Thiếu flag ⇒ NE3 abort.
- **Output bắt buộc**: narrative phải có mục **"Override đang hiệu lực"** liệt kê từng
  conflict_flag — người duyệt thấy ngay cái gì đang lệch chuẩn toàn cục và vì sao.

### S4 — Degraded environment deploy (triển khai trên hạ tầng suy giảm)

- **Layer A**: `node_health_index` tất định từ inventory (EOL date, tuổi kernel, incident
  rate 90 ngày). Ngưỡng index → chọn `restricted_change_protocol` từ bảng ngưỡng (L1/L2):
  canary % thấp hơn, cửa sổ bảo trì bắt buộc, cấm auto-restart dịch vụ nhạy trạng thái.
- **Logic**: tham số rollout lấy từ bảng ngưỡng trong KB — LLM không được chọn con số canary.
  Node quá ngưỡng đỏ ⇒ hard block "không deploy, cần thay node trước" và block đó chịu NE2.

### S5 — Black-swan structural nightmare (mâu thuẫn cấu trúc không hòa giải)

- **Định nghĩa**: chuẩn canonical L1 mâu thuẫn TRỰC TIẾP với thực địa — khác S3 ở chỗ không
  có override hợp lệ nào tồn tại (làm theo chuẩn thì hệ sập, làm theo thực địa thì phá chuẩn).
- **Logic — điều hệ CẤM làm**: tổng hợp một "phương án dung hòa" mượt mà che mâu thuẫn.
  Phát hiện mâu thuẫn (2 node active cùng scope cho chỉ thị loại trừ nhau, không flag nào
  hòa giải) ⇒ verdict **CONFLICT** + `CO_ESCALATED` ngay.
- **Plan B Architecture** là artifact RIÊNG, đánh dấu `plan_b: true` + điều kiện kích hoạt:
  chỉ được xây từ các node KHÔNG dính mâu thuẫn, mọi assertion vẫn qua đủ NE1–NE5. Người
  chọn plan — hệ không bao giờ tự failover kiến trúc (nhất quán D31: fallback hệ trọng không
  bao giờ tự động).

## §4 — Ma trận Never-Events NE1–NE5 → guardrail lập trình được

Tất cả **fail-closed**; vi phạm ⇒ abort + event, KHÔNG auto-fix. Đóng gói `scripts/gate_d32.sh`
(pattern `gate_m6.sh`) để CI làm chứng thực bên thứ ba (nguyên tắc G3).

| NE | Định nghĩa | Checker | Cơ chế | Hiện trạng |
|---|---|---|---|---|
| **NE1** | LLM sinh parameter/size/threshold không khớp Layer A | `check_output` | Exact match byte-level qua Numeric Firewall V24; nguồn đối chiếu = `LayerAResult` serialize + retrieved nodes | **ĐÃ CÓ** (`tools/guard/firewall.py`) — chỉ mở rộng nguồn |
| **NE2** | Sót hard block đã có trong KB | `check_completeness` (MỚI) | Chiều NGƯỢC firewall: mỗi `hard_blocks[i].subject` (kèm version string nguyên văn) phải xuất hiện trong prose — sót 1 ⇒ abort | D32.3 |
| **NE3** | L2 đè L1-security mà không có `conflict_flag` | `lint_conflict_flags` (MỚI) | Lint tất định trên retrieval set **TRƯỚC khi LLM chạy** (chặn sớm, rẻ) + kiểm lại sau khi sinh | D32.3 |
| **NE4** | Chỉ thị actionable thiếu citation inline | `check_citations_present` (MỚI) | Parser câu: câu chứa động từ chỉ thị (deploy/set/upgrade/pin/rollback/scale…) mà không mang token `[node_id]` hoặc `[layer_a:<formula_id>]` ⇒ vi phạm. Strict mode: MỌI câu trong section "Action" phải có citation | D32.3 |
| **NE5** | Citation bịa / trỏ tới chunk không tồn tại | `resolve_citations` (MỚI) | Exact lookup từng token về KB **và** phải thuộc retrieval set của chính run đó (chống bịa citation "nghe hợp lý" trỏ tới node có thật nhưng không được đọc) | D32.3 |

**Quan hệ với vòng rewrite (§2.5)**: NE1/NE4/NE5 cho phép viết lại (lỗi diễn đạt của LLM);
NE2 sau 1 lần nhắc mà vẫn sót ⇒ escalate thẳng; NE3 không có vòng viết lại — đó là lỗi dữ
liệu KB, phải sửa ở tầng ingest, không phải tầng prose.

## §5 — Roadmap hiện thực hóa (mỗi phase một TS riêng)

| Phase | Nội dung | Phụ thuộc |
|---|---|---|
| **D32.1** | KB SQLite FTS5 + metadata schema §1.2 + ingest bảng (nối Docling D31.5) + bảng `known_entities` tự build | Sau First Light; song song được với M7.x |
| **D32.2** | Layer A: schemas §2.1 + solver S1 + công thức sizing S2 + `node_health_index` S4 | D32.1 |
| **D32.3** | Agent-V mở rộng `extract_anchors` + Agent-R với 4 checker NE2–NE5 + `scripts/gate_d32.sh` | D32.2 |
| **D32.4** | Harness 5 scenario = 5 bộ fixture test offline + nối vào CI `test.yml` | D32.3 |

Điều kiện nghiệm thu kế thừa nguyên văn từ M6/M7: pytest toàn xanh, gate PASS, vùng cấm
nguyên vẹn, **PR thật với URL dạng `/pull/<số>`** — không link wizard, không tự khai.

## §6 — Rủi ro đã soi (red-team)

- **R1 — `known_entities` không phủ hết**: keyword-miss vẫn xảy ra khi query nhắc entity chưa
  từng vào KB. Chấp nhận được: khi đó vector recall gánh phần tìm, và NE5 bảo đảm không thể
  bịa nguồn cho entity không tồn tại — hệ trả "không có căn cứ trong KB" thay vì bịa.
- **R2 — NE4 là heuristic câu**: câu chỉ thị viết vòng ("nên cân nhắc nâng cấp…") có thể lọt
  parser động từ. Giảm thiểu: strict mode buộc citation trên MỌI câu của section Action;
  narrative template cố định section — chỉ thị nằm ngoài section Action là vi phạm cấu trúc.
- **R3 — trần rewrite 2 tạo nhiều escalation khi model yếu**: đây là hành vi MONG MUỐN
  (bảo thủ như tie-breaker D30); đo bằng metric escalation-rate trong `runs.report_json`,
  hiệu chuẩn model/prompt dựa trên số liệu thật — đúng trình tự First Light → M7.2.
- **R4 — Layer A sai thì firewall vô dụng** (garbage-in): Layer A là pure functions nên
  kiểm bằng property-based test + fixture chuẩn ở D32.4; firewall chỉ bảo đảm prose trung
  thành với Layer A, không bảo đảm Layer A đúng — trách nhiệm đó thuộc test G4 (business
  invariants), tách bạch rõ.
