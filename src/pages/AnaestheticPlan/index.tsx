import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { usePlanStore } from '@/store/planStore'
import { Step1Patient } from './Step1Patient'
import { Step2Surgery } from './Step2Surgery'
import { Step3Plan } from './Step3Plan'

const STEPS = [
  { label: 'Bệnh nhân',   short: '1' },
  { label: 'Phẫu thuật',  short: '2' },
  { label: 'Kế hoạch',    short: '3' },
]

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-6">
      {STEPS.map((s, i) => {
        const idx = i + 1
        const done = idx < current
        const active = idx === current
        return (
          <div key={i} className="flex items-center flex-1 last:flex-none">
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold border-2 transition-colors ${
                done
                  ? 'bg-sky-600 border-sky-600 text-white'
                  : active
                    ? 'bg-transparent border-sky-500 text-sky-400'
                    : 'bg-transparent border-slate-700 text-slate-600'
              }`}
            >
              {done ? '✓' : s.short}
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`h-0.5 flex-1 mx-1 transition-colors ${
                  done ? 'bg-sky-600' : 'bg-slate-700'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function AnaestheticPlan() {
  const navigate = useNavigate()
  const { step, nextStep, prevStep, resetWizard } = usePlanStore()

  function handleReset() {
    resetWizard()
  }

  return (
    <div className="px-4 py-6 max-w-lg mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={() => navigate('/')}
          className="flex items-center justify-center h-10 w-10 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white"
          aria-label="Quay về trang chủ"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">Kế hoạch Gây mê</h1>
          <p className="text-xs text-slate-400">
            {STEPS[step - 1].label} — Bước {step}/3
          </p>
        </div>
      </div>

      <StepIndicator current={step} />

      {step === 1 && <Step1Patient onNext={nextStep} />}
      {step === 2 && <Step2Surgery onNext={nextStep} onBack={prevStep} />}
      {step === 3 && <Step3Plan onBack={prevStep} onReset={handleReset} />}
    </div>
  )
}
