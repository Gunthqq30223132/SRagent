import { useState } from 'react'
import { ChevronLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { DoseResult } from '@/components/medical/DoseResult'
import { WarningBanner } from '@/components/medical/WarningBanner'
import { usePatientStore } from '@/store/patientStore'
import { calculateNmbDose } from '@/core/calculators/drugDosing'
import type { DoseResult as DoseResultType } from '@/types/medical'

const NMB_DRUGS = [
  { value: 'rocuronium' as const,     label: 'Rocuronium (Esmeron)',              rsi: true },
  { value: 'vecuronium' as const,     label: 'Vecuronium (Norcuron)',             rsi: false },
  { value: 'succinylcholine' as const, label: 'Suxamethonium (Succinylcholine)', rsi: true },
  { value: 'atracurium' as const,     label: 'Atracurium (Tracrium)',             rsi: false },
]

type DrugVal = typeof NMB_DRUGS[number]['value']

export default function MuscleRelaxantPage() {
  const navigate = useNavigate()
  const { patient, setWeight } = usePatientStore()

  const [drug, setDrug] = useState<DrugVal>('rocuronium')
  const [purpose, setPurpose] = useState<'intubation' | 'maintenance'>('intubation')
  const [isRsi, setIsRsi] = useState(false)
  const [result, setResult] = useState<DoseResultType | null>(null)

  const selectedDrug = NMB_DRUGS.find((d) => d.value === drug)!

  const handleCalculate = () => {
    setResult(calculateNmbDose({ drug, patient, purpose, isRsi }))
  }

  return (
    <div className="px-4 py-6 max-w-lg mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="min-h-[48px] min-w-[48px] flex items-center justify-center rounded-lg hover:bg-slate-800">
          <ChevronLeft className="h-6 w-6" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">Thuốc giãn cơ</h1>
          <p className="text-sm text-slate-400">Tính liều NMB · RSI · Duy trì</p>
        </div>
      </div>

      <section className="space-y-2">
        <p className="text-sm font-medium text-slate-400">Chọn thuốc giãn cơ</p>
        <div className="space-y-2">
          {NMB_DRUGS.map((d) => (
            <button key={d.value} onClick={() => { setDrug(d.value); setResult(null); if (!d.rsi) setIsRsi(false) }}
              className={`w-full rounded-xl border p-3 text-left min-h-[56px] transition-colors flex items-center justify-between ${
                drug === d.value
                  ? 'border-violet-500 bg-violet-950 text-violet-300'
                  : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500'
              }`}
            >
              <span className="font-medium text-sm">{d.label}</span>
              {d.rsi && <span className="text-xs px-2 py-0.5 rounded-full bg-red-900 text-red-300">RSI</span>}
            </button>
          ))}
        </div>
      </section>

      {/* Mục đích */}
      <div className="grid grid-cols-2 gap-2">
        {(['intubation', 'maintenance'] as const).map((p) => (
          <button key={p} onClick={() => { setPurpose(p); setResult(null) }}
            className={`min-h-[48px] rounded-lg border font-medium text-sm transition-colors ${
              purpose === p
                ? 'border-sky-500 bg-sky-950 text-sky-300'
                : 'border-slate-700 bg-slate-800 text-slate-300'
            }`}
          >
            {p === 'intubation' ? 'Đặt NKQ' : 'Duy trì'}
          </button>
        ))}
      </div>

      {/* RSI toggle */}
      {selectedDrug.rsi && purpose === 'intubation' && (
        <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-800 p-4 min-h-[56px]">
          <div>
            <p className="font-medium text-white text-sm">RSI (Rapid Sequence)</p>
            <p className="text-xs text-slate-400">Tăng liều để đặt NKQ nhanh hơn</p>
          </div>
          <button role="switch" aria-checked={isRsi} onClick={() => { setIsRsi((v) => !v); setResult(null) }}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors ${isRsi ? 'bg-red-600' : 'bg-slate-600'}`}
          >
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${isRsi ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>
      )}

      {drug === 'succinylcholine' && (
        <WarningBanner level="danger" message="Succinylcholine: kiểm tra CHỐNG CHỈ ĐỊNH trước khi dùng (tăng Kali, tiền sử sốt ác tính, bỏng, chấn thương nghiền nát)." />
      )}

      <div className="space-y-1">
        <label className="text-xs text-slate-400">Cân nặng bệnh nhân (kg)</label>
        <input type="number" min={1} max={300} step={0.5} value={patient.weightKg}
          onChange={(e) => { setWeight(Number(e.target.value)); setResult(null) }}
          className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-xl font-bold text-amber-400 tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
        />
      </div>

      <Button size="lg" fullWidth onClick={handleCalculate}>Tính liều giãn cơ</Button>

      {result && <DoseResult result={result} />}
    </div>
  )
}
