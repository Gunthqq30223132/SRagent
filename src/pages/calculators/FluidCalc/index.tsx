import { useState } from 'react'
import { ChevronLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Droplets } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { WarningBanner } from '@/components/medical/WarningBanner'
import { calculateFluid, getFluidStrategy } from '@/core/calculators/fluidCalculator'
import { usePatientStore } from '@/store/patientStore'
import type { FluidResult } from '@/types/medical'

type SurgeryType = 'minor' | 'moderate' | 'major'

const SURGERY_OPTIONS: { value: SurgeryType; label: string; example: string }[] = [
  { value: 'minor',    label: 'Phẫu thuật nhỏ',   example: 'Nội soi, phẫu thuật ngắn' },
  { value: 'moderate', label: 'Phẫu thuật vừa',   example: 'Bụng, lồng ngực' },
  { value: 'major',    label: 'Phẫu thuật lớn',   example: 'Tim, đại tràng, hồi sức' },
]

export default function FluidCalcPage() {
  const navigate = useNavigate()
  const { patient, setWeight } = usePatientStore()

  const [nilByMouth, setNilByMouth] = useState(6)
  const [duration, setDuration] = useState(2)
  const [surgeryType, setSurgeryType] = useState<SurgeryType>('moderate')
  const [result, setResult] = useState<FluidResult | null>(null)
  const [strategy, setStrategy] = useState<ReturnType<typeof getFluidStrategy> | null>(null)

  const handleCalculate = () => {
    const r = calculateFluid({
      weightKg: patient.weightKg,
      nilByMouthHours: nilByMouth,
      surgeryDurationHours: duration,
      surgeryType,
    })
    setResult(r)
    setStrategy(getFluidStrategy(r.intraopEstimate, duration))
  }

  return (
    <div className="px-4 py-6 max-w-lg mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="min-h-[48px] min-w-[48px] flex items-center justify-center rounded-lg hover:bg-slate-800">
          <ChevronLeft className="h-6 w-6" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">Tính lượng dịch truyền</h1>
          <p className="text-sm text-slate-400">Công thức 4-2-1 · Holliday-Segar</p>
        </div>
      </div>

      <section className="space-y-3">
        <p className="text-sm font-medium text-slate-400">Thông số bệnh nhân</p>

        <div className="space-y-1">
          <label className="text-xs text-slate-400">Cân nặng (kg)</label>
          <input type="number" min={1} max={300} step={0.5} value={patient.weightKg}
            onChange={(e) => { setWeight(Number(e.target.value)); setResult(null) }}
            className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-xl font-bold text-amber-400 tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Thời gian nhịn (giờ)</label>
            <input type="number" min={0} max={24} step={0.5} value={nilByMouth}
              onChange={(e) => { setNilByMouth(Number(e.target.value)); setResult(null) }}
              className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-lg font-bold text-white tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Thời gian mổ (giờ)</label>
            <input type="number" min={0.5} max={12} step={0.5} value={duration}
              onChange={(e) => { setDuration(Number(e.target.value)); setResult(null) }}
              className="w-full rounded-lg bg-slate-800 border border-slate-600 px-3 py-3 text-lg font-bold text-white tabular-nums text-center focus:border-sky-500 focus:outline-none min-h-[56px]"
            />
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs text-slate-400">Loại phẫu thuật</p>
          {SURGERY_OPTIONS.map((opt) => (
            <button key={opt.value} onClick={() => { setSurgeryType(opt.value); setResult(null) }}
              className={`w-full rounded-xl border p-3 text-left min-h-[56px] transition-colors ${
                surgeryType === opt.value
                  ? 'border-sky-500 bg-sky-950 text-sky-300'
                  : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500'
              }`}
            >
              <p className="font-semibold text-sm">{opt.label}</p>
              <p className="text-xs opacity-60">{opt.example}</p>
            </button>
          ))}
        </div>
      </section>

      <Button size="lg" fullWidth onClick={handleCalculate}>
        Tính lượng dịch
      </Button>

      {result && strategy && (
        <div className="rounded-xl border border-cyan-800 bg-cyan-950 p-5 space-y-4">
          <div className="flex items-center gap-2 text-cyan-300">
            <Droplets className="h-5 w-5" />
            <h3 className="font-semibold">Kết quả ước tính</h3>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Metric label="Duy trì (ml/h)" value={`${result.maintenancePerHour} mL`} />
            <Metric label="Bù thiếu hụt (ml)" value={`${result.deficitReplacement} mL`} />
            <Metric label="Tổng trong mổ (ml)" value={`${result.intraopEstimate} mL`} big />
          </div>

          <div className="bg-cyan-900/40 rounded-lg p-3 space-y-2">
            <p className="text-xs text-cyan-400 uppercase tracking-wide">Chiến lược truyền dịch</p>
            <div className="grid grid-cols-3 gap-2 text-center text-sm">
              <div><p className="text-xs text-slate-400">Giờ 1</p><p className="font-bold text-white">{strategy.hour1} mL</p></div>
              <div><p className="text-xs text-slate-400">Giờ 2</p><p className="font-bold text-white">{strategy.hour2} mL</p></div>
              <div><p className="text-xs text-slate-400">Các giờ sau</p><p className="font-bold text-white">{strategy.hourly} mL/h</p></div>
            </div>
          </div>

          <WarningBanner
            level="info"
            message={`Dịch khuyến nghị: ${result.recommendedFluid}. Điều chỉnh theo đáp ứng lâm sàng, CVP, và mất máu thực tế.`}
          />
        </div>
      )}
    </div>
  )
}

function Metric({ label, value, big = false }: { label: string; value: string; big?: boolean }) {
  return (
    <div className={big ? 'col-span-2 text-center' : ''}>
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`font-bold tabular-nums ${big ? 'text-3xl text-amber-400' : 'text-xl text-white'}`}>{value}</p>
    </div>
  )
}
