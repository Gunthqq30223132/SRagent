# D33 — Tách Kho dữ liệu (Corpus) khỏi Hàng đợi duyệt (Review Queue)

> **Vai trò**: đặc tả thiết kế cho O-1. Hiện thực do S-1/S-2 (Sonnet) thực hiện theo hợp đồng dưới đây.
> **Động cơ**: định vị SR-Agent là *multi-source → data warehouse → bài SR chuẩn Q1*.
> Schema hiện tại phục vụ mục tiêu cũ (hàng đợi duyệt 5/ngày), không phục vụ được mục tiêu mới.
> **Trạng thái**: THIẾT KẾ — chưa hiện thực. Cần chốt 3 quyết định ở §6 trước khi code.

---

## §1. Ba mâu thuẫn giữa schema hiện tại và định vị mới

### 1.1. Kho dữ liệu đang XOÁ dữ liệu

`sr_agent/store/staging.py:236`

```python
self.conn.execute("DELETE FROM documents WHERE uid = ?", (uid,))
```

Bản ghi không được Approve/Reject trong `TTL_HOURS = 72` bị **xoá vĩnh viễn**. Thiết kế này
đúng với mục tiêu cũ (chống tồn đọng cho người duyệt), nhưng kho thì **tích luỹ**, không trục xuất.

Hệ quả thực tế: mỗi bài SR phải thu thập lại từ đầu; không trả lời được câu hỏi
*"chủ đề này đã từng quét chưa, quét ngày nào, ra bao nhiêu kết quả"* — mà đó chính là
thông tin PRISMA 2020 bắt buộc phải báo cáo.

### 1.2. Không có chiều `review_id` — một paper không tái dùng được cho hai bài SR

Đây là rào cản **nặng hơn** vấn đề TTL, và chưa từng được nêu ở D30–D32.

| Bảng | Khoá hiện tại | Vấn đề |
|---|---|---|
| `documents.rubric_score` | 1 điểm / 1 uid | Rubric là **hàm của protocol**. Cùng paper, hai protocol khác nhau ⇒ hai điểm khác nhau. Chỉ lưu được một |
| `screening` | `uid` | Phán quyết include/exclude gắn với **tiêu chí của một review cụ thể**. Hai review sẽ ghi đè nhau |
| `extraction` | `uid` | Trường trích xuất phụ thuộc PICO của review. Tương tự |
| `documents.status` | 1 status / 1 uid | Một paper có thể `queued` ở review A và `rejected` ở review B cùng lúc — biểu diễn không được |

Không có `review_id` thì SR-Agent chỉ chạy được **đúng một bài SR tại một thời điểm**,
và bài thứ hai sẽ phá dữ liệu bài thứ nhất. Kho dùng chung là vô nghĩa.

### 1.3. Chiến lược tìm kiếm không được lưu — PRISMA 2020 mục 7 không đáp ứng được

Q1 bắt buộc báo cáo **query nguyên văn từng CSDL, ngày chạy, bộ lọc**, đủ để người khác
tái lập. Hiện `runs` chỉ lưu `query` thô ở mức batch, không gắn review, không gắn nguồn,
không lưu bộ lọc.

---

## §2. Mô hình 4 tầng đề xuất

```
CORPUS          bằng chứng thư mục — VĨNH VIỄN, append-only, không bao giờ DELETE
  │             (uid, source, payload, sha256, retracted)
  ├── REVIEWS   một bài SR = một review, protocol đóng băng bằng sha256
  │     │
  │     ├── REVIEW_QUEUE     trạng thái duyệt theo (review_id, uid) — PHÙ DU, TTL/WIP ở đây
  │     ├── SCREENING        + review_id
  │     ├── EXTRACTION       + review_id
  │     └── SEARCH_RUNS      query nguyên văn từng nguồn (PRISMA mục 7)
  └── (dlq, events, alerts giữ nguyên — vốn đã đúng vai)
```

**Bất biến nền tảng**: TTL chỉ được phép xoá dòng trong `review_queue`.
Xoá một dòng `corpus` là hành vi bị cấm ở tầng API — không có method nào expose nó.

## §3. Hợp đồng schema

```sql
-- TẦNG 1: kho bằng chứng, VĨNH VIỄN
CREATE TABLE corpus (
    uid               TEXT PRIMARY KEY,   -- ieee:12345678 | arxiv:2401.12345 | pmid:39012345
    source            TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    title_normalized  TEXT NOT NULL,
    payload           TEXT NOT NULL,      -- Document JSON (metadata + abstract + sections)
    content_sha256    TEXT NOT NULL,      -- phát hiện nguồn sửa metadata giữa 2 lần quét
    first_fetched_at  TEXT NOT NULL,
    last_refreshed_at TEXT NOT NULL,
    retracted         INTEGER NOT NULL DEFAULT 0,   -- cờ rút bài
    retracted_note    TEXT
);
CREATE INDEX idx_corpus_source ON corpus(source);
CREATE INDEX idx_corpus_title  ON corpus(title_normalized);

-- TẦNG 2: một bài SR
CREATE TABLE reviews (
    review_id       TEXT PRIMARY KEY,     -- uuid hoặc slug-ngày
    slug            TEXT NOT NULL UNIQUE,
    protocol_json   TEXT NOT NULL,        -- PICO + tiêu chí, đóng băng
    protocol_sha256 TEXT NOT NULL,        -- protocol đổi ⇒ review MỚI, không sửa tại chỗ
    registered_id   TEXT,                 -- PROSPERO, nếu có
    status          TEXT NOT NULL,        -- draft | screening | extraction | synthesis | frozen
    created_at      TEXT NOT NULL,
    frozen_at       TEXT
);

-- TẦNG 3: trạng thái duyệt — PHÙ DU, đây là nơi TTL/WIP tác động
CREATE TABLE review_queue (
    review_id           TEXT NOT NULL REFERENCES reviews(review_id),
    uid                 TEXT NOT NULL REFERENCES corpus(uid),
    status              TEXT NOT NULL,
    rubric_score        REAL,             -- điểm THEO protocol của review này
    last_interaction_at TEXT NOT NULL,
    notion_page_id      TEXT,
    PRIMARY KEY (review_id, uid)
);
CREATE INDEX idx_rq_status ON review_queue(review_id, status);

-- TẦNG 3: dấu vết tìm kiếm — PRISMA 2020 mục 7
CREATE TABLE search_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id    TEXT NOT NULL REFERENCES reviews(review_id),
    source       TEXT NOT NULL,
    query_string TEXT NOT NULL,           -- NGUYÊN VĂN, đủ để copy-paste tái lập
    filters_json TEXT NOT NULL DEFAULT '{}',
    executed_at  TEXT NOT NULL,
    n_returned   INTEGER NOT NULL
);

-- Sidecar M6: thêm review_id
ALTER TABLE screening  ADD COLUMN review_id TEXT;   -- + backfill, xem §4
ALTER TABLE extraction ADD COLUMN review_id TEXT;
```

## §4. Kế hoạch di trú (cho S-1)

Dữ liệu hiện có phải giữ nguyên vẹn — không được mất bản ghi nào.

1. Tạo bảng mới cạnh bảng cũ; **chưa xoá `documents`**.
2. `INSERT INTO corpus` từ `documents` (uid, source, title_normalized, payload, fetched_at).
   `content_sha256` tính từ `payload`. `retracted = 0`.
3. Tạo một review "legacy" (`slug = 'legacy-import'`, protocol rỗng có ghi chú) rồi
   `INSERT INTO review_queue` từ `documents` (status, rubric_score, last_interaction_at, notion_page_id).
4. Backfill `screening.review_id` và `extraction.review_id` = review legacy.
5. Chạy đối chiếu: `COUNT(documents) == COUNT(corpus) == COUNT(review_queue)`; mọi `uid` khớp.
6. Chỉ khi bước 5 xanh mới đổi `StagingStore` sang bảng mới. **`documents` giữ lại thêm
   một vòng phát hành** rồi mới `DROP` ở PR riêng — rollback rẻ.

**Tiêu chí nghiệm thu S-1**: `purge_expired()` xoá dòng `review_queue` nhưng
`SELECT COUNT(*) FROM corpus` **không đổi**. Có test khẳng định đúng điều này.

## §5. Ảnh hưởng tới vùng cấm (cần change control)

Việc hiện thực D33 **chạm vào file đang bị `gate_m6.sh` khoá zero-touch**:

| File | Có trong vùng cấm? | Vì sao phải sửa |
|---|---|---|
| `sr_agent/store/staging.py` | Không | Nơi đặt schema — sửa tự do |
| `sr_agent/models/schemas.py` | **CÓ** | `DocStatus` cần trạng thái theo review, không theo document |
| `sr_agent/pipeline.py` | **CÓ** | Pipeline phải nhận `review_id` khi ghi trạng thái |
| `sr_agent/config.py` | **CÓ** | Nếu tách `TTL_HOURS` (queue) khỏi chính sách lưu giữ corpus |

⇒ **Không thể hiện thực D33 mà không có ngoại lệ vùng cấm được phê duyệt trước.**
Đây là change request phải chốt trước khi giao S-1, không phải xin lỗi sau.

## §6. Ba quyết định cần chủ dự án chốt

| # | Quyết định | Vì sao phải chốt | Ảnh hưởng nếu chọn sai |
|---|---|---|---|
| Q-1 | Protocol sửa ⇒ tạo **review mới** hay cập nhật review cũ? | Đề xuất: review mới (protocol_sha256 là bất biến). Q1 đòi protocol đóng băng trước khi sàng lọc | Cho sửa tại chỗ ⇒ mất tính tái lập, reviewer Q1 bắt lỗi ngay |
| Q-2 | Corpus có giới hạn lưu giữ nào không (dung lượng/thời gian)? | SQLite một file; corpus tăng đơn điệu | Không đặt trần ⇒ file phình; đặt trần sai ⇒ quay lại đúng vấn đề đang sửa |
| Q-3 | Có chấp nhận **ngoại lệ vùng cấm** §5 không? | D33 buộc phải sửa `schemas.py`/`pipeline.py` | Không chấp nhận ⇒ D33 bế tắc, kho không tách được, định vị warehouse không thành |
