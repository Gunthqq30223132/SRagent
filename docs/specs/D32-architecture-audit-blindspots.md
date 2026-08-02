# D32 — Kiểm toán kiến trúc SR-Agent/AnesthOS & phân tích điểm mù

> **Vai trò tài liệu**: kiểm toán độc lập bản thiết kế 4 lớp + 7 cổng + khung AGENTS.md **trước khi**
> bàn giao cho AI Executor (Gemini Spark). Không phải tài liệu thiết kế mới — là danh sách điểm mù,
> kèm tang chứng tái lập được và các sửa đổi bắt buộc đưa vào Spec.
> **Phạm vi**: `SRagent/` (Lớp A–D, guard, harness) + `AnesthOS-app/` (ranh giới domain/UI).
> **Tang chứng**: `docs/audit/probe_clinical_gaps.py` — chạy được, tái lập được mọi con số dưới đây.

---

## §0. Phán quyết tổng thể

Bản thiết kế **đúng về mặt học thuyết** — "LLM đề xuất, verifier tất định định đoạt", fail-closed,
human-gate, tách seam. Ba trụ cột này không cần sửa. Nhưng có một khoảng cách nghiêm trọng giữa
*học thuyết* và *hiện thực đang có*, và một lớp điểm mù *cấu trúc* mà 7 cổng hiện tại không thể
nhìn thấy dù có hiện thực hoàn hảo đến đâu.

**Ba phát hiện chặn bàn giao (BLOCKER):**

| # | Phát hiện | Tang chứng |
|---|---|---|
| B1 | **Firewall V24 mù 100% với số liệu lâm sàng.** Nó được xây cho hằng số CS (port, O(n), GHz, %). Không có regex nào bắt `mg`, `mcg`, `mL`, `mmHg`, `IU`, `mEq`. 9/10 mẫu tấn công lâm sàng LỌT QUA. | `probe_clinical_gaps.py` PROBE 1 |
| B2 | **`anchors_checked == 0` ⇒ `passed = True`.** Văn bản không bóc được anchor nào thì mặc nhiên hợp lệ. Đây chính là *vacuous PASS* — thứ mà lằn ranh đỏ #4 cấm — nằm ngay trong lõi G1. | `firewall.py:136` (`passed=not violations`) |
| B3 | **G2 De-ID không tồn tại cho bệnh án tiếng Việt.** Một đoạn bệnh án đủ tên, tuổi, MSBA, giường, khoa, BHYT, ngày vào viện, SĐT bàn, tên+địa chỉ người nhà → **0 finding**. | `probe_clinical_gaps.py` PROBE 2 |

**Hai phát hiện High trong `AnesthOS-app` (lỗi sống, đang ở nhánh chính):**

| # | Phát hiện | Tang chứng |
|---|---|---|
| B4 | **`ibw.ts:82` clamp thầm lặng** — vi phạm trực tiếp BS-B. Trẻ sơ sinh 50 cm → IBW = **50 kg**. Sai số ~17 lần trên một hàm dùng để tính liều theo cân nặng. Qua đủ 5 cổng CI. | mục §1.6 |
| B5 | **`check-boundary.ts` bỏ lọt 8/8 API bị BS-F cấm** — `localStorage`, `window`, `document`, `XMLHttpRequest`, `WebSocket`, `performance.now()`, `crypto.randomUUID()`, `fetch` qua bí danh. Cổng in "✅ PASSED". | mục §1.7 |

---

## §1. Lỗ hổng an toàn lâm sàng (G1–G7)

### 1.1. G1 — Firewall mù với đơn vị lâm sàng (BLOCKER B1)

`_ANCHOR_PATTERNS` (`tools/guard/firewall.py:38-51`) có 6 pattern, danh sách đơn vị là
`ms|ns|µs|GHz|MHz|Hz|GB|MB|KB|TB|Gbps|Mbps|FLOPS|W|kW|B|tokens?|params?`.
**Không có một đơn vị lâm sàng nào.** Ngoài ra `AnchorKind` khai báo `"number_series"` nhưng
**không có regex tương ứng** — tức là không hề có luật bắt số trần.

Hệ quả đo được:

```
"Khởi mê propofol 2 mg/kg"  ->  extract_anchors() = []  ->  anchors_checked=0  ->  passed=True
```

Nguồn nói 1.5 mg/kg, LLM nói 2 mg/kg, firewall **thông qua**. Đây là kịch bản quá liều propofol
33% đi thẳng ra màn hình bác sĩ mà không cổng nào chạm vào.

### 1.2. G1 — So khớp substring gây PASS SAI (nguy hiểm hơn cả mù)

`check_output` dùng `needle in src` (`firewall.py:122`) — substring, không có ranh giới từ.
Do đó **con số nhỏ hơn được "chứng thực" bởi con số lớn hơn chứa nó**:

| Đầu ra LLM | Nguồn thật | Kết quả | Sai lệch lâm sàng |
|---|---|---|---|
| `5 mg` | `25 mg` | **PASS** (`"5 mg"` là substring của `"25 mg"`) | thiếu liều 5 lần |
| `9.9%` | `99.9%` | **PASS** — anchor được bóc, được đối chiếu, và khớp | sai 10 lần |
| `1.5` | `11.5` | **PASS** | — |

Nghịch lý đáng chú ý: test gốc của repo (`99.9 → 99.8` bị chặn) vẫn xanh, nên lỗ hổng này
hoàn toàn vô hình với bộ test hiện tại. **Sửa bắt buộc**: needle phải được neo ranh giới
(`(?<![\d.,])` … `(?![\d.,])`) trên *cả hai* phía, hoặc tốt hơn — xem §1.5.

### 1.3. Range holes, số viết bằng chữ, sai đơn vị

Ba lớp lách mà đề bài nêu đều **đã được xác nhận là có thật**:

- **Range hole**: `"2-3 mcg/kg"`. Kể cả khi đã thêm `mcg` vào danh sách đơn vị, regex
  `\d+\s?mcg` chỉ khớp `"3 mcg"` — **cận dưới `2` không bao giờ trở thành anchor**. Nếu nguồn
  có "3 mcg/kg" thì cả câu PASS trong khi cận dưới là bịa. Áp dụng y hệt cho `"5-10 ngày"`,
  `"mỗi 4-6 giờ"`, `"ASA II-III"`.
- **Số bằng chữ**: `"hai mg"`, `"nửa ống"`, `"gấp đôi liều"`, `"liều thứ ba"`, `"độ III"`
  (số La Mã), `"1/2 ống"` (phân số). Không pattern nào chạm tới.
- **Sai đơn vị**: `"1 mg/kg"` vs nguồn `"1 mcg/kg"` — sai 1000 lần trên adrenaline.
  Vì `mg` không nằm trong danh sách, không có anchor nào được sinh ra để so.

### 1.4. Điểm mù CẤU TRÚC: cơ chế slot chưa được đặc tả đủ (quan trọng nhất)

Đây là lớp điểm mù mà **không cổng G1–G7 nào có thể bắt được** vì nó không nằm ở chữ số.
`ClinicalPayloadItem` đang là `{slot_id, value, unit, provenance_id, coverage_flag}` — thiếu
mọi thứ cần để ràng buộc *ngữ nghĩa* quanh con số:

| Lỗ hổng | Ví dụ | Vì sao G1–G7 mù |
|---|---|---|
| **Đơn vị nằm ngoài slot** | LLM viết `Liều {{propofol_dose}} mcg/kg` trong khi payload có `unit = mg/kg` | LLM *đã gõ* đơn vị. Đơn vị là một dạng chữ số. G1 chỉ soi `value`. |
| **Đảo cực (polarity flip)** | `KHÔNG được vượt quá {{max_dose}}` ⇄ `Được dùng tới {{max_dose}}` | Số hoàn toàn đúng, provenance đúng, citation đúng. Nghĩa ngược 180°. Cả 7 cổng PASS. |
| **Sai phạm vi áp dụng** | `{{adult_dose}} cho trẻ em` | Payload không mang `population`/`route`/`indication` nên không có gì để đối chiếu. |
| **Slot bị bỏ rơi** | LLM lược mất `{{contraindication_warning}}` | G7 chặn khi *thiếu dữ liệu*, không chặn khi *LLM bỏ dùng dữ liệu đã có*. |
| **Slot dùng lặp mâu thuẫn** | `{{dose}}` xuất hiện ở hai câu trái nghĩa nhau | Không có ràng buộc bội số slot. |

**Khuyến nghị cấu trúc (bắt buộc, ưu tiên #1):**

```python
class ClinicalPayloadItem(BaseModel):
    slot_id: str
    value_type: Literal["point", "range", "threshold", "categorical"]
    value: Decimal | None = None          # point
    low: Decimal | None = None            # range — cận dưới là DỮ LIỆU, không phải chữ LLM gõ
    high: Decimal | None = None
    unit: str                             # nằm TRONG slot, LLM không được gõ đơn vị
    polarity: Literal["max_limit", "min_limit", "target", "informational"]
    applicability: Applicability          # population, age_band, route, indication, renal/hepatic
    contraindication_refs: list[str]
    provenance_id: str
    coverage_flag: Literal["covered", "gap", "conflict"]
    render_string: str                    # CHUỖI DUY NHẤT được phép chạm màn hình
    render_sha256: str                    # G1 đối chiếu hash, không đối chiếu regex
```

Đưa `low`/`high` vào một slot **đóng lại range hole bằng kiến trúc**, không phải bằng regex:
dải `2-3 mg/kg` render thành một chuỗi nguyên khối do Lớp A phát ra; LLM không bao giờ có cơ hội
gõ cận dưới.

### 1.5. Đảo G1 từ blacklist sang whitelist — khuyến nghị giá trị cao nhất

Mọi lỗ hổng §1.1–§1.3 đều cùng một gốc: G1 đang **đi tìm số sai trong văn bản LLM**. Đó là bài
toán blacklist — luôn thua vì không gian biến thể là vô hạn (dải, chữ số toàn phần `１２`,
chữ số Ả Rập `٢`, khoảng trắng không ngắt, số bằng chữ, số La Mã…).

Đảo ngược thành **strip-and-verify** (chứng dương, không thể lách):

```
1. Nhận TEMPLATE từ LLM (chưa điền slot).
2. Gỡ toàn bộ span {{slot_id}} khỏi template.
3. Phần còn lại là văn xuôi 100% do LLM viết. BẮT BUỘC:
      re.search(r'[\d٠-٩０-９]', prose)  is None
      and  không chứa token nào trong LEXICON_SỐ_BẰNG_CHỮ (vi + en)
   Có bất kỳ chữ số nào sống sót ngoài slot  =>  TỪ CHỐI VÔ ĐIỀU KIỆN.
4. Chỉ sau khi bước 3 sạch mới điền slot bằng render_string của Lớp A.
5. Sau khi điền: assert số chữ số trong đầu ra == tổng chữ số của các render_string đã dùng.
```

Bước 3 biến "LLM tuyệt đối không gõ chữ số" từ *lời hứa trong prompt* thành **bất biến kiểm tra
được**. Bước 5 chặn việc LLM chèn thêm số sau khi điền. Danh sách đơn vị lâm sàng vẫn nên bổ sung
(để bắt hồi quy), nhưng nó không còn là tuyến phòng thủ chính.

**Kèm theo, sửa B2**: `FirewallVerdict` phải có `expected_slot_count` và
`passed = (not violations) and (slots_rendered == expected_slot_count)`. `anchors_checked == 0`
với một payload lâm sàng khác rỗng phải là **FAIL**, không phải PASS.

### 1.6. G2 — De-ID trước bệnh án free-text (BLOCKER B3)

`tools/guard/outbound.py` được viết cho ngữ liệu *paper CS*, nơi PHI là ngẫu nhiên. Với AnesthOS,
PHI **chính là payload**. Kết quả đo trên một đoạn bệnh án tiếng Việt điển hình: **0 finding**.

Từng trường lọt lưới và lý do:

| Trường PHI | Vì sao lọt |
|---|---|
| Họ tên BN + người nhà | Không có rule tên; regex bắt *định dạng*, tên là *ngữ nghĩa* |
| Tuổi (`67 tuổi`) | Không có rule; HIPAA coi tuổi >89 là identifier, VN chưa quy định rõ nhưng tuổi + khoa + ngày = tái định danh |
| MSBA `1234567` | `CCCD_VN` chỉ bắt đúng **12** chữ số; mã bệnh án thường 7–10 số |
| BHYT `DN4010112345678` | Không có rule mã BHYT (2 chữ + 13 số) |
| SĐT bàn `02838221234` | `PHONE_VN` chỉ bắt di động (đầu 3/5/7/8/9), bỏ toàn bộ số cố định |
| Ngày vào viện `12/03/2026` | Không có rule ngày |
| Giường/khoa `giường 12 khoa GMHS` | Không có rule định vị nội viện |
| Chẩn đoán hiếm gặp | Bệnh hiếm + khoa + tỉnh = tái định danh gần như chắc chắn |

Spec D31 §5 gọi tầng NER là "mở rộng tương lai". **Với ngữ liệu lâm sàng, đánh giá đó phải đảo
lại**: NER/de-ID là điều kiện tiên quyết, không phải phần thêm.

**Khuyến nghị G2:**
1. Bổ sung rule regex: `MSBA/MHS \d{6,12}`, mã BHYT, SĐT cố định (mã vùng 02x), ngày `dd/mm/yyyy`,
   `giường|buồng|phòng \d+`, số bảo hiểm xã hội.
2. Thêm tầng NER offline (ONNX, PhoBERT-NER hoặc tương đương) cho PERSON/LOC/ORG/DATE —
   chạy local, không mâu thuẫn BS-F.
3. **Đổi mô hình tin cậy từ blacklist sang allowlist cho trường lâm sàng**: payload rời máy phải
   là *structured*, mỗi trường được khai báo tường minh là an toàn để xuất. Free-text bệnh án
   **mặc định CẤM xuất**, muốn xuất phải qua bước con người duyệt từng đoạn.
4. **Biến "interceptor" thành interceptor thật.** Hiện `assert_sanitized()` là hàm *ai đó phải nhớ
   gọi*; một provider mới quên gọi là xuất thô. Bọc ở tầng transport (custom `httpx.Transport`)
   để egress **không thể xảy ra về mặt vật lý** nếu chưa qua guard.

### 1.7. G6 — Citation-orphan không ràng buộc số với nguồn của nó

`check_output` dùng `any(needle in src for src in norm_sources)` — một con số hợp lệ **ở bất kỳ
nguồn nào** đều chứng thực cho câu trích dẫn **bất kỳ nguồn nào khác**. Đã đo: LLM viết
"Theo [A], liều là 8 mg" trong khi A nói 4 mg và B (chủ đề khác) nói 8 mg → **PASS**.

G6 kiểm `article_id` có tồn tại; không ai kiểm *con số này đến từ đúng article đó*.
**Sửa**: `NumericAnchor` phải mang `claimed_source_uid`, và đối chiếu chỉ được thực hiện với
`source_texts[claimed_source_uid]` — không phải với cả kho.

### 1.8. G3/G4 — chống làm dịu cảnh báo là bài toán không giải được bằng keyword

G3 (contraindication) và G4 (terminology-lock) đang được đặc tả như *danh sách từ khóa*.
Hai vấn đề:

- **Blacklist thua paraphrase.** Bề mặt phủ định tiếng Việt rất rộng: `không`, `chưa`, `hiếm khi`,
  `ít khi cần`, `thường không bắt buộc`, `có thể cân nhắc bỏ qua`, `trong đa số trường hợp là an toàn`.
  Không danh sách nào phủ hết.
- **Dùng LLM làm judge thì vi phạm lằn ranh đỏ #7** (cấm gọi LLM trong hàm kiểm tra của Agent-V).

**Lối ra duy nhất nhất quán với học thuyết**: câu cảnh báo/chống chỉ định **không được sinh tự do**.
Chúng phải là slot y hệt chữ số — `{{contraindication_block}}` render nguyên khối từ Lớp A.
G4 khi đó chuyển từ "dò từ cấm" thành hai phép kiểm tất định, đều làm được:
1. **Toàn vẹn**: mọi `contraindication_refs` của các slot đã dùng phải xuất hiện đủ trong đầu ra
   (thiếu một cái = FAIL — chống *lược bỏ* cảnh báo).
2. **Bất khả xâm phạm**: span của khối cảnh báo sau khi render phải khớp **byte-exact** với
   `render_string` gốc — chống *sửa lời* cảnh báo. LLM không được viết chữ nào bên trong span đó.

---

## §2. Mức sẵn sàng cho Gemini Spark (khung AGENTS.md)

### 2.1. Stop-token do chính executor gõ ra thì không phải là cổng

`PLAN_READY`, `APPROVED`, `GATE_PASS` hiện là **chuỗi ký tự**. Một LLM có thể in ra chữ
`GATE_PASS` bất cứ lúc nào — đây là reward-hacking cách một câu văn.

**Sửa (bắt buộc)**: token phải do tiến trình mà agent *không thể tự tạo* phát hành.

```
APPROVED_TOKEN = HMAC-SHA256(
    key   = khoá nằm NGOÀI workspace của agent (env của runner / CI secret),
    msg   = git_tree_sha ‖ test_digest ‖ plan_sha ‖ phase ‖ iteration
)
```
Pha 4 từ chối khởi động nếu token không verify được với `git_tree_sha` **hiện tại**. Hệ quả phụ
rất đẹp: agent sửa bất kỳ file nào sau khi được duyệt → tree sha đổi → token vô hiệu.

### 2.2. Cấm nhảy pha phải cưỡng chế bằng cơ chế, không bằng lời

"Pha 2 cấm gõ code" hiện chỉ là câu lệnh trong prompt. **Sửa**: ghi `git rev-parse HEAD` +
`git stash create` lúc vào Pha 2; Pha 3 (VERIFY GATE) từ chối cấp token nếu working tree đã đổi.
Rẻ, tất định, không thể lách.

### 2.3. `dev_gate.py ≤ 3 lặp` — hành vi ở lần thứ 4 chưa được định nghĩa

Đặc tả không nói gì sau lần lặp thứ 3. **Khoảng trống đặc tả là nơi LLM tự quyết**, và nó sẽ
quyết theo hướng "nới test cho xanh". Phải ghi rõ:

```
Lần lặp 4  =>  DỪNG CỨNG.
             git checkout tới snapshot Pha 3 (huỷ toàn bộ thay đổi Pha 4)
             ghi run_manifest.json với trạng thái GATE_EXHAUSTED + log 3 lần thất bại
             escalate cho người; TUYỆT ĐỐI không tự nới tiêu chí
Bộ đếm lặp lưu NGOÀI workspace agent (nếu không, agent sẽ sửa bộ đếm).
```

### 2.4. Chống sửa test (reward-hacking) — lỗ hổng lớn nhất của gate hiện có

`scripts/gate_m6.sh:65` chỉ grep `assert True|mark.skip|mark.xfail`. Lách được ngay bằng:
`assert  True` (hai dấu cách), `assert 1`, `assert x == x`, `pytest.skip()` gọi trong thân hàm,
`@pytest.mark.parametrize` với danh sách rỗng. Và quan trọng hơn cả — **gate không hề phát hiện
việc XOÁ test**. Gemini Spark chỉ cần xoá bài test đang đỏ là cổng xanh.

Tỉ lệ `assert/test ≥ 1.0` cũng là chỉ số gameable: thêm `assert result is not None` là qua.

**Sửa (bắt buộc, đưa vào `dev_gate.py`)**:
```
1. RATCHET SỐ LƯỢNG: pytest --collect-only -q  >=  baseline ghi trong APPROVED token.
2. TESTS CHỈ ĐƯỢC CỘNG: git diff --numstat <snapshot> -- tests/  =>  số dòng XOÁ phải = 0,
   trừ khi implementation_plan.md khai báo tường minh file test được sửa.
3. KIỂM TRA ĐỘT BIẾN (mutation smoke): cố ý đảo 1 hằng số trong code vừa viết,
   chạy lại test — test PHẢI đỏ. Test không đỏ = test rỗng nghĩa => FAIL.
4. CẤM SỬA CỔNG: dev_gate.py, forbidden_patterns.py, scripts/gate_*.sh, .github/workflows/**
   nằm trong forbidden paths VÀ được đối chiếu hash trong CI.
```
Điểm 4 là điều kiện sống còn: **một cái cổng mà agent sửa được thì không phải là cổng.**

### 2.5. Gate hiện tại đang PASS RỖNG (lỗi sống)

`scripts/gate_m6.sh:25` trỏ `BASE_REF="origin/claude/sr-agent-pipeline-design-rqtctp"`.
Nhánh này **không còn tồn tại** (`git rev-parse` → `fatal: Needed a single revision`).
Dòng 48-50 xử lý bằng cách **bỏ qua toàn bộ kiểm tra zero-touch** rồi vẫn cho phép in
`[PASS] Sprint M6 verification PASSED!`.

Nghĩa là: cổng bảo vệ vùng cấm `sr_agent/config.py`, `router.py`, `schemas.py`, `pipeline.py`,
`pyproject.toml` **hiện đang tắt mà không ai biết**. Đây đúng là mẫu vi phạm lằn ranh đỏ #4
(vacuous PASS) nằm ngay trong công cụ thực thi lằn ranh đỏ.
**Sửa**: base ref vắng mặt phải là `exit 1`, không bao giờ là `skip`. Nguyên tắc chung cho mọi
cổng: *không kiểm được ≠ đạt*.

### 2.6. Bổ sung bắt buộc cho `implementation_plan.md` (Pha 2)

Trả lời trực tiếp câu hỏi 2b. Mười mục dưới đây phải có, nếu thiếu thì Pha 3 không cấp token:

1. **File ownership allowlist** — liệt kê chính xác đường dẫn được tạo/sửa. Chạm file ngoài danh sách = FAIL.
2. **Forbidden paths** — `sr_agent/config.py`, `sr_agent/ingest/router.py`, `sr_agent/models/schemas.py`,
   `tools/guard/**`, `dev_gate.py`, `forbidden_patterns.py`, `.github/workflows/**`, `pyproject.toml`.
3. **Hợp đồng API công khai** — chữ ký hàm + kiểu đầy đủ, chốt trước khi viết. Executor không được tự thiết kế lại.
4. **Test baseline** — số lượng + tên các test hiện phải tiếp tục xanh (đầu vào của ratchet §2.4).
5. **Test mới khai báo trước theo TÊN và theo Ý ĐỒ ASSERT** — không cho phép "sẽ viết test phù hợp".
6. **Tiêu chí chấp nhận PHỦ ĐỊNH** — "thay đổi này KHÔNG được làm X pass", "KHÔNG được đụng Y".
   Tiêu chí chỉ-có-mặt-tích-cực là lời mời gaming.
7. **Ngân sách tất định** — model id ghim kèm digest, `temperature=0`, `seed`, phiên bản dữ liệu.
8. **Mục "known-unknowns"** — điều executor phải **DỪNG và hỏi** thay vì đoán. Không có mục này,
   LLM luôn chọn đoán.
9. **Kế hoạch rollback** — lệnh cụ thể để hoàn nguyên.
10. **Tuyên bố ngoài phạm vi** — cái gì *không* làm trong lần này.

### 2.7. Rủi ro trôi context (context rot)

Đề bài hỏi thẳng về điểm này. Ba nguồn trôi cụ thể:

- **Bất biến bị pha loãng theo độ dài hội thoại.** 8 lằn ranh đỏ nêu ở đầu phiên sẽ mờ dần sau
  vài chục lượt. *Sửa*: `dev_gate.py` là nguồn chân lý duy nhất — bất biến được **thực thi bằng máy
  mỗi lần chạy**, không dựa vào việc agent còn nhớ. Prompt nhắc lại; máy mới là thứ cưỡng chế.
- **Trôi giữa các pha.** SPEC nói A, đến EXECUTE thành A'. *Sửa*: `plan_sha` nằm trong HMAC (§2.1) —
  plan đổi thì token chết.
- **Trôi giữa các phiên/agent.** *Sửa*: `run_manifest.json` mỗi lần chạy ghi model id + digest +
  plan_sha + tree_sha + kết quả từng cổng. Đây vừa là chống trôi, vừa là hồ sơ audit lâm sàng.

---

## §3. Tính đầy đủ của `forbidden_patterns.py` — 11 luật cần bổ sung

8 luật hiện có đều đúng và nên giữ. Chúng phủ *lỗi hạ tầng RAG*. Cái thiếu là *lỗi số học lâm sàng*
và *lỗi tự đánh giá*. Đề nghị thêm:

| # | Luật mới | Mẫu cần bắt | Vì sao |
|---|---|---|---|
| 9 | **Clamp/bão hoà thầm lặng** | `Math.max(0,`, `Math.min(`, `np.clip`, `\|\| 0`, `?? 0`, `.get(k, 0)`, `float(x or 0)` | Vi phạm BS-B. **Đang có thật ở `ibw.ts:82`** — xem §1.6 phần AnesthOS |
| 10 | **Tham số LLM phi tất định** | `temperature` khác 0, thiếu `seed`, thiếu `schema_model` ở lời gọi structured | Tất định là nền của toàn bộ verifier |
| 11 | **Model tag không ghim** | `:latest`, tên model không kèm digest | Bài học `gemma3:4b`→`gemma4:e4b` của M6-hotfix chưa được máy hoá |
| 12 | **Nội dung truy xuất nội suy thẳng vào prompt** | f-string chèn `doc.content` vào system prompt | **Prompt injection — hiện không có phòng thủ nào trong toàn bộ thiết kế.** Một PDF độc có thể ép làm dịu chống chỉ định (đánh G3) hoặc gán sai trích dẫn (đánh G6) |
| 13 | **Sửa/xoá test** | diff `tests/` có dòng bị xoá; `assert\s+True`, `assert 1`, `pytest.skip(` | §2.4 |
| 14 | **`except` rộng bao quanh bước KIỂM TRA** | `except Exception` ôm trọn hàm verify/extract | `evidence_extract.py:166` nuốt lỗi → tài liệu lỗi trông giống tài liệu "không có bằng chứng". Với G7 đây là **fail-OPEN**: sự cố bị nhầm thành GAP |
| 15 | **Số thực nhị phân cho liều** | `float` cho giá trị liều; `round()` trước khi cộng dồn | `ibw.ts` làm tròn IBW *trước* khi tính ABW → sai số cộng dồn. Liều phải dùng `Decimal`/số nguyên micro-đơn vị |
| 16 | **Phi tất định trong verifier** | `datetime.now()`, `random`, locale, thứ tự `set`/`dict` ảnh hưởng phán quyết | Verifier không tất định thì không phải verifier |
| 17 | **Hằng số lâm sàng hardcode trong mã nguồn** | literal số đi kèm đơn vị lâm sàng nằm ngoài dataset có provenance | Bản sao phía mã nguồn của Zero-Hallucination: số phải sống trong dữ liệu có nguồn, không nằm trong `.py`/`.ts` |
| 18 | **Ghi vào bảng audit/provenance ngoài hàm được phép** | tổng quát hoá luật #3 sang `provenance`, `run_manifest`, `guard_audit` | Hồ sơ audit bị sửa = mất toàn bộ giá trị pháp lý |
| 19 | **Cổng bị sửa** | diff chạm `dev_gate.py`, `forbidden_patterns.py`, `scripts/gate_*.sh`, `.github/workflows/**` | §2.4 điểm 4 |

**Lưu ý hiện thực**: `forbidden_patterns.py` nên chạy trên **AST**, không phải grep. Grep thua
khoảng trắng, xuống dòng, bí danh — chính xác như cách `gate_m6.sh` đang thua.

---

## §4. Seam offline/cloud — bốn mâu thuẫn cần chốt trước khi code

### 4.1. Streaming ⊥ fail-closed (mâu thuẫn cứng)

Firewall phán quyết trên **đầu ra hoàn chỉnh**. Nếu UI stream token, con số chưa được kiểm
**đã nằm trên màn hình bác sĩ** trước khi verdict tồn tại. Rút lại chữ đã hiện còn tệ hơn không hiện.

**Lối ra đẹp — và kiến trúc slot đã cho sẵn**: stream **template** (theo §1.5, template không chứa
một chữ số nào — an toàn tuyệt đối để hiện dần), giữ slot ở dạng ô xám placeholder; chạy G1–G7 khi
stream kết thúc; điền toàn bộ số **một lần, nguyên khối**. Vừa được cảm giác phản hồi tức thì,
vừa giữ fail-closed. Nên ghi thẳng điều này vào Spec Lớp C.

### 4.2. `SynthesisProvider` hứa nhiều hơn Gemini có thể giữ

Hợp đồng D31 §3 khai `synthesize(..., schema_model)` và `citations` **bắt buộc khác rỗng**.
Thực tế bất đối xứng:

| | Ollama/Gemma 3 4B | Gemini File Search |
|---|---|---|
| Structured output | constrained decoding theo JSON schema | `responseSchema` — **không phải lúc nào cũng kết hợp được với grounding** |
| Citations | **không có khái niệm citation** | có grounding chunks, nhưng theo **file id của Google**, không phải `SourceDoc.uid` |

Hệ quả: `OllamaProvider` **về mặt cấu trúc không thể** thoả `citations != []` nếu citation được kỳ
vọng đến từ model. **Sửa**: citation phải đến từ **bước truy xuất** (uid nào được nạp vào context),
không đến từ model. Và thêm `supports_schema: bool` vào Protocol; router **từ chối** (fail-closed)
tác vụ đòi schema trên provider không hỗ trợ — tuyệt đối không hạ cấp xuống parse regex văn xuôi.

### 4.3. Ánh xạ citation của Gemini là nơi G6 sẽ vỡ

Upload lên File Search ⇒ Google tự chunk và cấp id riêng. Ánh xạ ngược về `SourceDoc.uid`
**chưa được đặc tả** — và đó chính xác là nơi citation-orphan sẽ phát sinh trong thực tế.
Tệ hơn cho audit lâm sàng: upload lại ⇒ chunk khác ⇒ **citation không tái lập được giữa hai lần chạy**.
**Sửa**: ghim phiên bản corpus, lưu bảng ánh xạ `google_file_id ↔ uid` đã giải vào `run_manifest.json`;
G6 đối chiếu với bảng đã lưu, không đối chiếu trực tiếp với phản hồi API.

### 4.4. Ngân sách độ trễ và chuẩn hoá Unicode

- **Deadline**: fallback cloud→local (đúng, giữ nguyên) nhưng Gemma 4B local chậm hơn nhiều bậc.
  Nếu có deadline lâm sàng, người dùng sẽ nhận **timeout** thay vì đường lui. Phải chia ngân sách
  deadline riêng cho từng nhánh và định nghĩa hành vi khi nhánh lui cũng quá hạn (đề xuất: hiện
  "Cần tra cứu thủ công" — thống nhất với G7).
- **Unicode**: `_normalize` không chuẩn hoá NFC. Tiếng Việt có hai cách tổ hợp dấu; Gemini có thể
  trả về dạng khác nguồn ⇒ `verify_quote` **FAIL giả** thuần do mã hoá. Chuẩn hoá **NFC** ở cả hai
  phía. **Tuyệt đối không dùng NFKC** cho nội dung — NFKC biến `①`→`1`, `½`→`1/2`, tạo PASS giả.
  (NFKC chỉ được phép dùng trong bước *phát hiện* chữ số ở §1.5, không dùng cho nội dung.)

---

## §5. Ma trận rủi ro & việc phải làm trước khi giao Gemini Spark

### 5.1. Xếp hạng ưu tiên

| Mức | ID | Điểm mù | Việc phải làm | Repo |
|---|---|---|---|---|
| 🔴 **HIGH** | H1 | Firewall mù đơn vị lâm sàng; `anchors_checked=0` ⇒ PASS | Đảo sang strip-and-verify (§1.5) + `expected_slot_count` | SRagent |
| 🔴 **HIGH** | H2 | Substring khớp sai: `5 mg` PASS nhờ `25 mg` | Neo ranh giới hai phía trên needle | SRagent |
| 🔴 **HIGH** | H3 | `ClinicalPayloadItem` thiếu range/polarity/applicability | Mở rộng schema theo §1.4 | SRagent |
| 🔴 **HIGH** | H4 | G2 De-ID không bắt PHI bệnh án tiếng Việt | Rule VN + NER offline + allowlist trường + transport-level guard | SRagent |
| 🔴 **HIGH** | H5 | Stop-token do agent tự gõ | HMAC gắn `tree_sha ‖ plan_sha` (§2.1) | SRagent |
| 🔴 **HIGH** | H6 | Gate không phát hiện xoá/nới test | Ratchet + tests-chỉ-cộng + mutation smoke (§2.4) | SRagent |
| 🔴 **HIGH** | H7 | `gate_m6.sh` đang PASS RỖNG (base ref đã mất) | Ref vắng mặt ⇒ `exit 1` | SRagent |
| 🔴 **HIGH** | H8 | `ibw.ts:82` clamp thầm lặng — trẻ 50cm ⇒ IBW 50kg | Ném `ClinicalValidationError` khi ngoài vùng áp dụng Devine | AnesthOS |
| 🟠 **MED** | M1 | G6 không ràng buộc số với đúng nguồn | `claimed_source_uid` trong anchor | SRagent |
| 🟠 **MED** | M2 | G3/G4 chống làm dịu bằng keyword — thua paraphrase | Cảnh báo thành slot nguyên khối + kiểm toàn vẹn/byte-exact (§1.8) | SRagent |
| 🟠 **MED** | M3 | Không có phòng thủ prompt-injection từ ngữ liệu | Phân tách data/instruction + luật #12 | SRagent |
| 🟠 **MED** | M4 | `check-boundary.ts` bỏ lọt 8/8 API bị cấm | Xem §5.2 — sửa bằng `tsconfig`, không bằng thêm regex | AnesthOS |
| 🟠 **MED** | M5 | CI không chạy trên nhánh `claude/*` | Thêm `claude/**` vào trigger — hiện agent làm việc ở nhánh **không có cổng nào** | AnesthOS |
| 🟠 **MED** | M6 | Hành vi lần lặp thứ 4 chưa định nghĩa | Dừng cứng + rollback + escalate (§2.3) | SRagent |
| 🟠 **MED** | M7 | Streaming mâu thuẫn fail-closed | Stream template, điền slot sau verdict (§4.1) | SRagent |
| 🟠 **MED** | M8 | Citation Gemini không tái lập được | Ghim corpus + lưu bảng ánh xạ (§4.3) | SRagent |
| 🟡 **LOW** | L1 | Không có gate cho BS-C (provenance) | Test phản chiếu: mỗi calculator phải có `*_PROVENANCE` hợp lệ + `lastReviewedDate` chưa quá hạn | AnesthOS |
| 🟡 **LOW** | L2 | Ngưỡng coverage 60% quá thấp cho tier CLINICAL | ≥90% **branch** cho `calculators/**`; mỗi mã `ClinicalValidationError` phải có ≥1 test | AnesthOS |
| 🟡 **LOW** | L3 | Chuẩn hoá Unicode (NFC) thiếu | NFC hai phía; cấm NFKC cho nội dung | SRagent |
| 🟡 **LOW** | L4 | `redact()` bỏ qua finding chồng lấn một phần | Gộp span trước khi che (các ca lồng nhau đã thử đều an toàn, nhưng vòng lặp không có bước merge) | SRagent |
| 🟡 **LOW** | L5 | Làm tròn float trước khi cộng dồn (`ibw.ts`) | Làm tròn **một lần** ở bước hiển thị | AnesthOS |

### 5.2. Ghi chú riêng cho `AnesthOS-app`

**H8 — clamp thầm lặng (`src/domain/calculators/ibw.ts:82`)**

```ts
const inchesOver5Feet = Math.max(0, heightInches - 60);   // <-- clamp
```
Đo thực tế:

| Chiều cao | IBW trả về | Đúng ra phải |
|---|---|---|
| 175 cm | 70.5 kg | 70.5 kg ✅ |
| 140 cm | **50 kg** | ném lỗi |
| 90 cm | **50 kg** | ném lỗi |
| 50 cm (sơ sinh) | **50 kg** | ném lỗi |
| 1 cm | **50 kg** | ném lỗi |

Công thức Devine không có hiệu lực dưới 5 ft (152.4 cm). `Math.max(0, …)` biến "ngoài vùng áp dụng"
thành "trả liều nền 50 kg" — đúng nguyên văn thứ BS-B cấm ("never return clipped default values when
inputs are out of bounds"). Với trẻ sơ sinh đây là sai số ~17 lần trên một hàm dùng để tính liều.
Qua đủ **cả 5 cổng CI**.
*Sửa*: `heightCm < 152.4` ⇒ `throw new ClinicalValidationError('HEIGHT_BELOW_FORMULA_DOMAIN', …)`;
bệnh nhi cần calculator riêng có provenance riêng. Cũng nên siết cận dưới hợp lệ (hiện chấp nhận 1 cm).

**M4 — `check-boundary.ts` bỏ lọt toàn bộ**

Một file domain chứa `localStorage`, `window`, `document`, `new XMLHttpRequest()`, `new WebSocket()`,
`performance.now()`, `crypto.randomUUID()`, `fetch` gán qua bí danh, `new Date()` qua bí danh,
`toLocaleString()` → cổng in `✅ Domain Boundary Validation Passed`. **8/8 lọt.**

Không nên chữa bằng cách thêm chuỗi vào danh sách cấm — bí danh và truy cập gián tiếp luôn thắng
so-khớp-tên. **Sửa đúng là dùng trình biên dịch**: `src/domain` có `tsconfig` riêng với
`"lib": ["ES2022"]` (**bỏ `DOM`**). Khi đó `window`/`document`/`fetch`/`localStorage`/`XMLHttpRequest`
trở thành **lỗi biên dịch** — không thể lách bằng bí danh. Giữ `check-boundary.ts` cho phần
`Math.random`/`Date.now`/import UI mà type system không diễn đạt được.

**M5 — CI không phủ nhánh agent**

`.github/workflows/ci.yml` trigger `push: [main, develop, 'feat/*']`. Nhánh làm việc của agent là
`claude/**` ⇒ **không cổng nào chạy trên đúng nơi rủi ro cao nhất**. Thêm `claude/**` (và
`agent/**` để khớp quy ước worktree của D31 §2).

### 5.3. Thứ tự khuyến nghị

```
ĐỢT 0 — phải xong TRƯỚC KHI giao bất cứ việc gì cho Gemini Spark (cổng phải đáng tin trước đã)
   H7 (gate hết PASS rỗng) · H5 (HMAC token) · H6 (chống sửa test) · M5 (CI phủ nhánh agent)
   + viết forbidden_patterns.py (19 luật, chạy trên AST) + dev_gate.py, và ĐƯA CHÍNH CHÚNG
     vào forbidden paths có đối chiếu hash.
   Lý do: giao việc khi cổng còn hổng thì mọi output đều phải kiểm tay lại — mất sạch lợi ích tự động hoá.

ĐỢT 1 — an toàn lâm sàng lõi (làm in-house, KHÔNG giao executor: đây là nơi không được sai)
   H3 (schema payload) · H1 (strip-and-verify) · H2 (neo ranh giới) · H8 (sửa ibw.ts)
   Lý do: H1 phụ thuộc H3 — sửa firewall trước khi chốt schema là làm hai lần.

ĐỢT 2 — có thể giao Gemini Spark, vì lúc này hợp đồng đã đóng cứng và cổng đã đáng tin
   H4 (rule De-ID VN + NER) · M1 · M2 · M3 · M4 · M7 · M8 · L1–L5
```

**Nguyên tắc phân công**: giao cho executor phần **hợp đồng đã đóng cứng và có test đối chứng**
(đúng cách D31.2 đã làm). Giữ in-house phần **định nghĩa bất biến an toàn** — vì một executor tự
định nghĩa tiêu chí an toàn của chính mình thì cổng chỉ còn là hình thức.

---

## §6. Tái lập kết quả

```bash
cd SRagent && python docs/audit/probe_clinical_gaps.py     # 9/10 lỗ hổng firewall, 7/7 PHI lọt
cd AnesthOS-app && npm run lint:boundary                   # PASS ngay cả với file vi phạm cố ý
```

Khi các khuyến nghị Đợt 1 hoàn tất, chuyển 10 ca của PROBE 1 thành test thật trong `tests/`
với kỳ vọng **đảo ngược** (phải CHẶN) — đó là tiêu chí nghiệm thu cho H1–H3.
