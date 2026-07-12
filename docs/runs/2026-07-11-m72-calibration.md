# Hồ sơ hiệu chuẩn M7.2 — chuỗi 2R → 2R2, quyết định model & phán quyết audit (2026-07-11)

> Executor: Antygravity trên MacBook Air M4 · Auditor (rater 2): Fable.
> Spec gốc: `docs/specs/M7.2-screening-calibration.md`. Corpus có nhãn vàng:
> tài liệu đúng chủ đề RAG + planted negatives (mồi exoplanet), uid mồi chốt trước khi chạy.

## 1. Chuỗi kết quả qua ba vòng

| Chỉ số (ngưỡng spec §3) | 2R: qwen2.5:7b | 2R2: **llama3.1:8b** | Phán quyết 2R2 |
|---|---|---|---|
| Invalid-rate A (≤20%) | 39.2% | **15.2%** (12/79) | ĐẠT |
| Invalid-rate B (≤20%) | 1.3% | **1.3%** (1/79) | ĐẠT |
| Mồi bị loại — A (≥12/15) | 0/15 | **13/15** | ĐẠT |
| Mồi bị loại — B (≥12/15) | 14/15 | **14/15** | ĐẠT |
| Include-rate A ([10,90]%) | 60.8% | **79.1%** (53/67) | ĐẠT |
| Include-rate B ([10,90]%) | 81.0% | **82.1%** (64/78) | ĐẠT |
| Cặp hợp lệ (≥50) | 48 | **66** | ĐẠT |
| Cohen's κ (≥0.4) | 1.00* (degenerate-lean) | **0.9042** | ĐẠT |

Corpus 2R2: 79 = 64 RAG + 15 mồi, DB `calib_m72_r22_llama.db`, screener B giữ `gemma4:e4b`.

## 2. Kiểm toán độc lập của Fable trên 2R2 — SẠCH

Toàn bộ số tự cộng khớp: 12/79 = 0.15190 ✓; 1/79 = 0.01266 ✓; 53/67 = 0.79104 ✓;
64/78 = 0.82051 ✓; 79 − 12 − 1 = 66 cặp (hai tập invalid rời nhau) ✓. Quan trọng nhất,
**κ tái tính độc lập từ chính bảng mồi + marginals của báo cáo**: trên 66 cặp chung,
đồng thuận 64/66 (2 bất đồng: mồi `2404.09350` A-include/B-exclude; 1 doc RAG
A-exclude/B-include), margins đối xứng 53/66 include mỗi bên
⇒ p_o = 0.9697, p_e = 0.6837, κ = 0.28604/0.31634 = **0.90421** — khớp báo cáo tới
5 chữ số thập phân. Đây là mức kiểm chứng mạnh nhất một báo cáo executor từng đạt.

**QUYẾT ĐỊNH**: `SR_SCREEN_MODEL_A=llama3.1:8b` là screener A chính thức
(gemma2:9b fallback không cần dùng). Lý do chọn llama thay gemma2 ngay từ mandate:
screener B đã là họ gemma — hai rater cùng họ chia sẻ điểm mù, mất giá trị độc lập.

## 3. Phase 3 (staging) — VÔ HIỆU, phải chạy lại đúng thủ tục

Báo cáo khai κ = 1.0 trên staging (20 doc RAG, 17 cặp, include 100% cả hai bên).
Ba lý do vô hiệu:

1. **Vi phạm C3**: executor "reset sạch lịch sử screening cũ trong staging DB" — thao
   tác ghi tay vào DB, đồng thời XÓA audit trail lịch sử (dữ liệu κ=0.00 của First
   Light là chứng cứ hiệu chuẩn gốc). Thủ tục đúng: backup DB → hỏi owner (C6) →
   namespace/DB mới.
2. **κ = 1.0 này là thống kê thoái hóa**: cả hai screener include 100% trên corpus
   không có negative nào (đã qua rubric gate) ⇒ p_e = 1, nhánh degenerate của
   `compute_cohen_kappa` trả 1.0. Không đo được năng lực phân biệt.
3. Với 17 cặp hợp lệ include-rate 100%, guard `SCREEN_DEGENERATE` PHẢI phát 2 event —
   báo cáo không nhắc tới ⇒ thiếu bằng chứng đối chiếu.

**κ chính thức của hệ song thẩm là 0.9042 (từ corpus có nhãn vàng 2R2)** — không phải
1.0. Con số staging chỉ nói: trên corpus toàn tài liệu hợp lệ, hai screener không loại
nhầm bài nào (một tín hiệu tốt, nhưng là tín hiệu khác).

## 4. Việc còn nợ sau vòng này

- Executor: dán event SCREEN_DEGENERATE của batch staging; xác nhận có backup staging
  DB trước khi reset hay không (nếu không: ghi nhận mất dữ liệu vào hồ sơ này).
- 3 file uncommitted trên máy Mac (notion_page.py song ngữ, staging.py
  check_same_thread, test fix) — phải đi đường PR; riêng `staging.py
  check_same_thread=False` bị bác: PR #13 đã fix đúng gốc (store per-rerun), nới
  check_same_thread toàn cục chỉ che race condition.
- Nợ treo GĐ6: `arxiv:2508.05650` vẫn chờ con người duyệt thật trong `make ui`.
