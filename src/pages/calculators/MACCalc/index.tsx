import { useState } from 'react'
import { ChevronLeft, Wind } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { WarningBanner } from '@/components/medical/WarningBanner'
import { calculateMAC } from '@/core/calculators/mac'
import { usePatientStore } from '@/store/patientStore'
import type { MACResult } from '@/core/calculators/mac'

const AGENTS = [
  { value: 'sevoflurane',   label: 'Sevoflurane',    mac: '2.0%' },
  { value: 'desflurane',    label: 'Desflurane',     mac: '6.0%' },
  { value: 'isoflurane',    label: 'Isoflurane',     mac: '1.15%' },
  { value: 'halothane',     label: 'Halothane',      mac: '0.75%' },
] as const

type AgentValue = typeof AGENTS[number]['value']

export default function MACCalcPage() {
  const navigate = useNavigate()
  const { patient, setAge } = usePatientStore()

  const [agent, setAgent] = useState<AgentValue>('sevoflurane')
  const [n2oPercent, setN2oPercent] = useState(0)
  const [targetMac, setTargetMac] = useState(1.0)
  const [result, setResult] = useState<MACResult | null>(null)

  const handleCalculate = () => {
    setResult(calculateMAC({ agent, ageYears: patient.ageYears, n2oPercent, targetMacFraction: targetMac }))
  }

  return (
    <div className="px-4 py-6 max-w-lg mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="min-h-[48px] min-w-[48px] flex items-center justify-center rounded-lg hover:bg-slate-800">
          <ChevronLeft className="h-6 w-6" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">Tính MAC thuốc bốc hơi</h1>
          <p className="text-sm text-slate-400">Minimum Alveolar Concentration</p>
        </div>
      </div>

      <section className="space-y-2">
        <p className="text-sm font-medium text-slate-400">Chọn thuốc bốc hơi</p>
        <div className="grid grid-cols-2 gap-2">
          {AGENTS.map((a) => (
            <button key={a.value} onClick={() => { setAgent(a.value); setResult(null) }}
              className={`min-h-[56px] rounded-xl border p-3 text-left transition-colors ${
                agent === a.value
                  ? 'border-emerald-500 bg-emerald-950 text-emerald-300'
                  : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500'
              }`}
            >
              <p className="font-semibold text-sm">{a.label}</p>
              <p className="text-xs opacity-60">MAC cơ bản: {a.mac}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Tuổi bệnh nhân (năm)</label>
            <input type="number" min={0} max={120} step={1} value={patient.ageYears}
              onChange={(e) => { setAge(Number(e.target.value)); setResult(null) }}
              className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-lg font-bold text-white tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-400">N₂O (%)</label>
            <input type="number" min={0} max={70} step={10} value={n2oPercent}
              onChange={(e) => { setN2oPercent(Number(e.target.value)); setResult(null) }}
              className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-lg font-bold text-white tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
            />
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-slate-400">Mục tiêu MAC (thường 0.7–1.3)</label>
          <input type="number" min={0.5} max={2.0} step={0.1} value={targetMac}
            onChange={(e) => { setTargetMac(Number(e.target.value)); setResult(null) }}
            className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-xl font-bold text-amber-400 tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
          />
        </div>
      </section>

      <Button size="lg" fullWidth onClick={handleCalculate}>Tính MAC</Button>

      {result && (
        <div className="rounded-xl border border-emerald-800 bg-emerald-950 p-5 space-y-4">
          <div className="flex items-center gap-2 text-emerald-300">
            <Wind className="h-5 w-5" />
            <h3 className="font-semibold">Kết quả MAC</h3>
          </div>

          <div className="text-center">
            <p className="text-xs text-slate-400 uppercase tracking-wide">Nồng độ cần đặt trên máy</p>
            <p className="text-5xl font-bold text-amber-400 tabular-nums mt-1">{result.targetConcentration}%</p>
            <p className="text-sm text-slate-400 mt-1">
              MAC hiệu chỉnh tuổi: {result.ageCorrectedMac}% (hệ số: {result.ageFactor})
            </p>
          </div>

          {n2oPercent > 0 && (
            <div className="flex justify-center gap-6 text-sm text-slate-400">
              <span>N₂O đóng góp: <span className="text-slate-200">{result.n2oEquivalent} MAC</span></span>
              <span>Còn cần: <span className="text-slate-200">{result.remainingMac} MAC</span></span>
            </div>
          )}

          {result.notes.map((note, i) => (
            <WarningBanner key={i} level="caution" message={note} />
          ))}
        </div>
      )}
    </div>
  )
}
