# 🧠 AnesthOS Dev Station — Cheatsheet

> **Phiên bản**: 2026-07-12 · **Máy**: MacBook Air M4 · **OS**: macOS Tahoe 26.3.1

---

## ⚡ 5 Lệnh Duy Nhất Cần Nhớ

| Lệnh | Khi nào dùng | Ghi chú |
|-------|-------------|---------|
| `anesthos-start` | Bắt đầu code session | Pull code → mở Claude Code qua OmniRoute |
| `anesthos-check` | Kiểm tra sức khỏe hệ thống | Test toàn bộ 4 model (Auto, Kiro, Antigravity, Ollama) |
| `anesthos-save` | Kết thúc code session | Commit + push cả code + AI history lên GitHub |
| `ollama serve` | Khi cần offline fallback | Khởi động Ollama nếu chưa chạy |
| `launchctl list \| grep anesthos` | Kiểm tra health agent | Phải thấy `com.anesthos.omniroute-health` |

---

## 🔄 Quy Trình Hàng Ngày

```
┌─ BẮT ĐẦU ──────────────────────────────────────────────┐
│  1. Mở Terminal                                         │
│  2. Gõ: anesthos-check                                  │
│     → Đảm bảo tất cả 4 model đều [WORKING]              │
│  3. Gõ: anesthos-start                                  │
│     → Tự động pull code mới từ GitHub                   │
│     → Tự động mở Claude Code qua OmniRoute              │
│  4. Code bình thường trong Claude Code                  │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─ CHUYỂN MODEL THỦ CÔNG / SONG SONG ─────────────────────┐
│  Trong giao diện Claude Code:                           │
│  • Mặc định: Dùng combo tự động (anesthos-brain)        │
│  • Chuyển thủ công sang Kiro AI:                        │
│    Gõ: /model kr/claude-sonnet-4.5                      │
│  • Chuyển thủ công sang Antigravity Cloud:              │
│    Gõ: /model antigravity/claude-sonnet-4-6             │
│  • Chuyển thủ công sang Ollama Local:                   │
│    Gõ: /model ollama/qwen2.5:7b-instruct                │
│  • Quay lại tự động:                                    │
│    Gõ: /model anesthos-brain                            │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─ KẾT THÚC ─────────────────────────────────────────────┐
│  1. Trong Claude Code, gõ: /exit                        │
│  2. Trong Terminal, gõ: anesthos-save                   │
│     → Hỏi xác nhận (y/n)                               │
│     → Commit + push code lên GitHub                     │
│     → Commit + push AI chat history lên repo riêng      │
└─────────────────────────────────────────────────────────┘
```

---

## 🏥 Quick Troubleshooting

| Triệu chứng | Nguyên nhân | Fix |
|-------------|-------------|-----|
| Claude Code báo "connection refused" | OmniRoute chưa chạy | `PORT=20128 DATA_DIR=~/.omniroute nohup omniroute &` |
| Bị lỗi API hoặc không biết model nào chạy | Kiểm tra sức khỏe | Gõ lệnh: `anesthos-check` |
| Notification "Restarting OmniRoute" | Health agent tự restart | Bình thường, tự phục hồi trong 10s |
| Notification "flapping limit" | OmniRoute crash 3+ lần/giờ | Fix thủ công: kiểm tra `~/.omniroute/health.log` |
| `anesthos-start` báo "SSD not found" | Thư mục project bị xóa | Kiểm tra `~/projects/AnesthOS` tồn tại |
| `anesthos-start` báo "SSH failed" | Không có internet/SSH key | Kiểm tra SSH: `ssh -T git@github.com` |
| Offline, không có AI | Chạy `ollama serve` trước | Model fallback: `ollama/qwen2.5:7b-instruct` |

---

## 📊 Component Status Check

```bash
# Kiểm tra nhanh tất cả các model:
anesthos-check

# Kiểm tra daemon status:
launchctl list | grep anesthos
```

---

## 🔑 Thông Tin Quan Trọng

| Key | Value |
|-----|-------|
| Project path | `~/projects/AnesthOS` |
| OmniRoute URL | `http://localhost:20128/v1` |
| Model combo | `anesthos-brain` |
| Claude profile | `~/.claude/profiles/anesthos/` |
| Health log | `~/.omniroute/health.log` |
| Code repo | `github.com/gunthqq30223132/9router` |
| History repo | `github.com/gunthqq30223132/AnesthOS-AI-History` |

