import { useState } from 'react'
import { ChevronLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { Button } from '@/components/ui/Button'
import { ASA_CRITERIA, calculateASAScore } from '@/core/calculators/asa'
import { usePatientStore } from '@/store/patientStore'
import type { ASAClass } from '@/types/medical'
import type { ASAResult } from '@/core/calculators/asa'

const ASA_CLASSES: ASAClass[] = ['I', 'II', 'III', 'IV', 'V', 'VI']

const riskColors: Record<ASAClass, string> = {
  I:   'border-green-600 bg-green-950 text-green-300',
  II:  'border-sky-600 bg-sky-950 text-sky-300',
  III: 'border-amber-600 bg-amber-950 text-amber-300',
  IV:  'border-orange-600 bg-orange-950 text-orange-300',
  V:   'border-red-600 bg-red-950 text-red-300',
  VI:  'border-slate-600 bg-slate-800 text-slate-300',
}

export default function ASAScorePage() {
  const navigate = useNavigate()
  const { setASA } = usePatientStore()
  const [selected, setSelected] = useState<ASAClass | null>(null)
  const [isEmergency, setIsEmergency] = useState(false)
  const [result, setResult] = useState<ASAResult | null>(null)

  const handleSelect = (cls: ASAClass) => {
    setSelected(cls)
    setResult(null)
  }

  const handleCalculate = () => {
    if (!selected) return
    const criteria: Partial<Record<ASAClass, boolean>> = { [selected]: true }
    const res = calculateASAScore({ selectedCriteria: criteria, isEmergency })
    setResult(res)
    setASA(selected)
  }

  return (
    <div className="px-4 py-6 max-w-lg mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center rounded-lg hover:bg-slate-800"
        >
          <ChevronLeft className="h-6 w-6" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">Phân loại ASA</h1>
          <p className="text-sm text-slate-400">ASA Physical Status Classification 2020</p>
        </div>
      </div>

      {/* ASA class selector */}
      <section className="space-y-2">
        <p className="text-sm font-medium text-slate-400">Chọn phân loại phù hợp</p>
        <div className="space-y-2">
          {ASA_CLASSES.map((cls) => {
            const criteria = ASA_CRITERIA[cls]
            const isSelected = selected === cls
            return (
              <button
                key={cls}
                onClick={() => handleSelect(cls)}
                className={clsx(
                  'w-full rounded-xl border p-4 text-left min-h-[72px] transition-all',
                  isSelected
                    ? riskColors[cls]
                    : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500',
                )}
              >
                <p className="font-semibold text-sm">{criteria.label}</p>
                <p className="text-xs mt-1 opacity-70 line-clamp-2">{criteria.description}</p>
              </button>
            )
          })}
        </div>
      </section>

      {/* Cấp cứu toggle */}
      <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-800 p-4 min-h-[56px]">
        <div>
          <p className="font-medium text-white text-sm">Phẫu thuật cấp cứu</p>
          <p className="text-xs text-slate-400">Thêm hậu tố "E" vào phân loại ASA</p>
        </div>
        <button
          role="switch"
          aria-checked={isEmergency}
          onClick={() => setIsEmergency((v) => !v)}
          className={clsx(
            'relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors',
            isEmergency ? 'bg-red-600' : 'bg-slate-600',
          )}
        >
          <span
            className={clsx(
              'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform',
              isEmergency ? 'translate-x-6' : 'translate-x-1',
            )}
          />
        </button>
      </div>

      <Button size="lg" fullWidth onClick={handleCalculate} disabled={!selected}>
        Xác nhận phân loại
      </Button>

      {/* Kết quả */}
      {result && (
        <div className={clsx('rounded-xl border p-5 space-y-3', riskColors[result.class])}>
          <p className="text-2xl font-bold">{result.emergencyLabel ?? result.label}</p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs opacity-60 uppercase tracking-wide">Nguy cơ phẫu thuật</p>
              <p className="font-semibold mt-0.5">{result.perioperativeRisk}</p>
            </div>
            <div>
              <p className="text-xs opacity-60 uppercase tracking-wide">Tỷ lệ tử vong</p>
              <p className="font-semibold mt-0.5">{result.mortalityRate}</p>
            </div>
          </div>
          {selected && (
            <div className="space-y-1">
              <p className="text-xs opacity-60 uppercase tracking-wide">Ví dụ lâm sàng</p>
              <ul className="text-sm space-y-1">
                {ASA_CRITERIA[selected].examples.map((ex, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="opacity-40 shrink-0">·</span>
                    <span>{ex}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
