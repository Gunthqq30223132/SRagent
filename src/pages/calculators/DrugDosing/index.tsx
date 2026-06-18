import { useState } from 'react'
import { ChevronLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { DoseResult } from '@/components/medical/DoseResult'
import { usePatientStore } from '@/store/patientStore'
import { calculateInductionDose } from '@/core/calculators/drugDosing'
import type { DoseResult as DoseResultType } from '@/types/medical'

type DrugOption = { value: 'propofol' | 'ketamine' | 'etomidate' | 'thiopental'; label: string }

const DRUG_OPTIONS: DrugOption[] = [
  { value: 'propofol',    label: 'Propofol (Diprivan)' },
  { value: 'ketamine',    label: 'Ketamin (Ketalar)' },
  { value: 'etomidate',   label: 'Etomidate (Hypnomidate)' },
  { value: 'thiopental',  label: 'Thiopental natri' },
]

export default function DrugDosingPage() {
  const navigate = useNavigate()
  const { patient, setWeight, setAge } = usePatientStore()

  const [selectedDrug, setSelectedDrug] = useState<DrugOption['value']>('propofol')
  const [result, setResult] = useState<DoseResultType | null>(null)

  const handleCalculate = () => {
    const res = calculateInductionDose({ drug: selectedDrug, patient })
    setResult(res)
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
          <h1 className="text-xl font-bold text-white">Tính liều khởi mê</h1>
          <p className="text-sm text-slate-400">Propofol · Ketamin · Etomidate · Thiopental</p>
        </div>
      </div>

      {/* Chọn thuốc */}
      <section className="space-y-2">
        <p className="text-sm font-medium text-slate-400">Chọn thuốc khởi mê</p>
        <div className="grid grid-cols-2 gap-2">
          {DRUG_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { setSelectedDrug(opt.value); setResult(null) }}
              className={`min-h-[48px] rounded-lg border px-3 py-2 text-sm font-medium text-left transition-colors ${
                selectedDrug === opt.value
                  ? 'border-sky-500 bg-sky-950 text-sky-300'
                  : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      {/* Thông tin bệnh nhân */}
      <section className="space-y-3">
        <p className="text-sm font-medium text-slate-400">Thông tin bệnh nhân</p>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Cân nặng (kg)</label>
            <input
              type="number"
              min={1} max={300} step={0.5}
              value={patient.weightKg}
              onChange={(e) => { setWeight(Number(e.target.value)); setResult(null) }}
              className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-xl font-bold text-amber-400 tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Tuổi (năm)</label>
            <input
              type="number"
              min={0} max={120} step={1}
              value={patient.ageYears}
              onChange={(e) => { setAge(Number(e.target.value)); setResult(null) }}
              className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-xl font-bold text-white tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <Button size="lg" fullWidth onClick={handleCalculate}>
        Tính liều
      </Button>

      {/* Kết quả */}
      {result && <DoseResult result={result} />}
    </div>
  )
}
