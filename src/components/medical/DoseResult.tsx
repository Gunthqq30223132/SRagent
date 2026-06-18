import { clsx } from 'clsx'
import { AlertTriangle, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import type { DoseResult as DoseResultType } from '@/types/medical'
import { WarningBanner } from './WarningBanner'

interface DoseResultProps {
  result: DoseResultType
}

export function DoseResult({ result }: DoseResultProps) {
  const [copied, setCopied] = useState(false)

  const summaryText = `${result.drugNameVn} (${result.drugName})\nLiều: ${result.recommendedDoseMg} mg${result.volumeMl ? ` / ${result.volumeMl} mL` : ''}\nĐường dùng: ${result.route}`

  const handleCopy = async () => {
    await navigator.clipboard.writeText(summaryText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className={clsx(
        'rounded-xl border p-4 space-y-3',
        result.isOverdose
          ? 'border-red-600 bg-red-950'
          : 'border-slate-700 bg-slate-800',
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm text-slate-400">{result.drugName}</p>
          <h3 className="text-lg font-semibold text-white">{result.drugNameVn}</h3>
        </div>
        <button
          onClick={handleCopy}
          title="Sao chép kết quả"
          className="rounded-lg p-2 text-slate-400 hover:text-white hover:bg-slate-700 min-h-[48px] min-w-[48px] flex items-center justify-center"
        >
          {copied ? <Check className="h-5 w-5 text-green-400" /> : <Copy className="h-5 w-5" />}
        </button>
      </div>

      {/* Main dose */}
      <div className="text-center py-2">
        {result.isOverdose && (
          <div className="flex items-center justify-center gap-1 text-red-400 mb-1">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-xs font-medium uppercase tracking-wide">Cảnh báo vượt liều</span>
          </div>
        )}
        <p
          className={clsx(
            'text-4xl font-bold tabular-nums',
            result.isOverdose ? 'text-red-400' : 'text-amber-400',
          )}
        >
          {result.recommendedDoseMg} mg
        </p>
        {result.volumeMl && (
          <p className="text-xl text-slate-300 mt-1 tabular-nums">
            = {result.volumeMl} mL
          </p>
        )}
        <p className="text-sm text-slate-400 mt-1">
          {result.concentration} · {result.route}
        </p>
      </div>

      {/* Range */}
      <div className="flex justify-center gap-6 text-sm text-slate-400">
        <span>Tối thiểu: <span className="text-slate-200">{result.minDoseMg} mg</span></span>
        <span>Tối đa: <span className="text-slate-200">{result.maxDoseMg} mg</span></span>
      </div>

      {/* Notes */}
      {result.notes && result.notes.length > 0 && (
        <div className="space-y-2 pt-1">
          {result.notes.map((note, i) => (
            <WarningBanner
              key={i}
              level={note.startsWith('⚠️') || note.includes('CHỐNG CHỈ ĐỊNH') ? 'danger' : 'caution'}
              message={note}
            />
          ))}
        </div>
      )}

      {/* Disclaimer nhỏ */}
      <p className="text-xs text-slate-500 border-t border-slate-700 pt-2">
        Kết quả chỉ mang tính tham khảo. Không thay thế đánh giá lâm sàng của bác sĩ.
      </p>
    </div>
  )
}
