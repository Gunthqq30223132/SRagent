# AnaesthesiaVN — Hỗ trợ Quyết định Lâm sàng Gây mê

Ứng dụng PWA hỗ trợ quyết định lâm sàng gây mê, được Việt hóa hoàn toàn cho thị trường Y tế Việt Nam.

## Tính năng Giai đoạn 1

| Công cụ | Mô tả |
|---|---|
| Tính liều khởi mê | Propofol, Ketamin, Etomidate, Thiopental — hiệu chỉnh tuổi/ASA |
| Thuốc giãn cơ | Rocuronium, Vecuronium, Succinylcholine, Atracurium — RSI support |
| Tính dịch truyền | Công thức 4-2-1 · Holliday-Segar · Chiến lược bù dịch |
| MAC thuốc bốc hơi | Sevoflurane, Desflurane, Isoflurane, Halothane — hiệu chỉnh tuổi + N₂O |
| Phân loại ASA | ASA I–VI + hậu tố E (cấp cứu) · Nguy cơ phẫu thuật |

## Stack

- **React 18 + TypeScript** (strict mode)
- **Vite 6** (build tool, code splitting)
- **Tailwind CSS** (dark mode mặc định — tối ưu cho phòng mổ)
- **Zustand** (state management)
- **React Router v6** (lazy loading)
- **vite-plugin-pwa + Workbox** (offline-first PWA)

## Phát triển

```bash
npm install
npm run dev        # http://localhost:5173
npm run type-check # TypeScript strict check
npm run build      # Production build + PWA
```

## Kiến trúc

```
src/
  core/calculators/   # Pure functions — zero React dependencies
  core/ai/            # LLMAdapter interface (Phase 2 ready)
  components/         # UI components (medical, layout, ui)
  pages/              # Route-level screens
  store/              # Zustand stores
  hooks/              # Custom hooks
```

## Pháp lý

Tuân thủ Nghị định 13/2023/NĐ-CP về Bảo vệ Dữ liệu Cá nhân.
Kết quả chỉ mang tính tham khảo — không thay thế phán đoán lâm sàng.
