import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Medical UI palette — tối ưu cho đèn phẫu thuật
        medical: {
          bg: '#0f172a',        // Nền chính (slate-900)
          surface: '#1e293b',   // Card surface (slate-800)
          border: '#334155',    // Viền (slate-700)
          accent: '#38bdf8',    // Accent xanh dương (sky-400)
          success: '#4ade80',   // OK / an toàn (green-400)
          warning: '#fbbf24',   // Cảnh báo / kết quả (amber-400)
          danger: '#f87171',    // Nguy hiểm / quá liều (red-400)
          muted: '#94a3b8',     // Text phụ (slate-400)
        },
      },
      fontSize: {
        // Đảm bảo đọc được dưới đèn phẫu thuật
        'dose': ['1.5rem', { lineHeight: '2rem', fontWeight: '700' }],
      },
      minHeight: {
        'touch': '48px',  // WCAG 2.5.5 touch target minimum
      },
      minWidth: {
        'touch': '48px',
      },
    },
  },
  plugins: [],
} satisfies Config
