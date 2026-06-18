import { usePlanStore } from '@/store/planStore'
import { Button } from '@/components/ui/Button'
import type { AgeUnit } from '@/types/medical'

const AGE_UNIT_LABELS: Record<AgeUnit, string> = {
  years: 'Tuổi (năm)',
  months: 'Tháng',
  days: 'Ngày',
}

function computeAgeYears(value: number, unit: AgeUnit): number {
  if (unit === 'years') return value
  if (unit === 'months') return Math.max(value / 12, 0.08)
  return Math.max(value / 365, 0.003)
}

export function Step1Patient({ onNext }: { onNext: () => void }) {
  const { patient, setPatient } = usePlanStore()

  const bmi =
    patient.heightCm && patient.heightCm > 0
      ? Math.round((patient.weightKg / (patient.heightCm / 100) ** 2) * 10) / 10
      : null

  function handleAgeUnitChange(unit: AgeUnit) {
    const ageYears = computeAgeYears(patient.ageValue, unit)
    setPatient({ ageUnit: unit, ageYears })
  }

  function handleAgeValueChange(value: number) {
    const ageYears = computeAgeYears(value, patient.ageUnit)
    setPatient({ ageValue: value, ageYears })
  }

  function addAllergy(val: string) {
    const trimmed = val.trim()
    if (trimmed && !patient.allergies.includes(trimmed)) {
      setPatient({ allergies: [...patient.allergies, trimmed] })
    }
  }

  function removeAllergy(item: string) {
    setPatient({ allergies: patient.allergies.filter((a) => a !== item) })
  }

  function addMed(val: string) {
    const trimmed = val.trim()
    if (trimmed && !patient.currentMedications.includes(trimmed)) {
      setPatient({ currentMedications: [...patient.currentMedications, trimmed] })
    }
  }

  function removeMed(item: string) {
    setPatient({ currentMedications: patient.currentMedications.filter((m) => m !== item) })
  }

  const isValid = patient.weightKg > 0 && patient.ageValue > 0

  return (
    <div className="space-y-6">
      {/* Giới tính */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Giới tính</label>
        <div className="flex gap-3">
          {(['male', 'female'] as const).map((sex) => (
            <button
              key={sex}
              onClick={() => setPatient({ sex })}
              className={`flex-1 min-h-[48px] rounded-xl border text-sm font-semibold transition-colors ${
                patient.sex === sex
                  ? 'bg-sky-900 border-sky-500 text-sky-300'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
              }`}
            >
              {sex === 'male' ? '♂ Nam' : '♀ Nữ'}
            </button>
          ))}
        </div>
      </div>

      {/* Tuổi */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Tuổi</label>
        <div className="flex gap-2">
          <input
            type="number"
            min={0}
            value={patient.ageValue || ''}
            onChange={(e) => handleAgeValueChange(Number(e.target.value))}
            className="flex-1 min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-white text-lg px-4 tabular-nums focus:outline-none focus:border-sky-500"
            placeholder="0"
          />
          <select
            value={patient.ageUnit}
            onChange={(e) => handleAgeUnitChange(e.target.value as AgeUnit)}
            className="min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-slate-300 px-3 focus:outline-none focus:border-sky-500"
          >
            {(['years', 'months', 'days'] as AgeUnit[]).map((u) => (
              <option key={u} value={u}>{AGE_UNIT_LABELS[u]}</option>
            ))}
          </select>
        </div>
        {patient.ageUnit !== 'years' && patient.ageValue > 0 && (
          <p className="text-xs text-slate-500 mt-1">
            ≈ {Math.round(patient.ageYears * 10) / 10} năm tuổi
          </p>
        )}
      </div>

      {/* Cân nặng + Chiều cao */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Cân nặng (kg)
          </label>
          <input
            type="number"
            min={0.5}
            step={0.5}
            value={patient.weightKg || ''}
            onChange={(e) => setPatient({ weightKg: Number(e.target.value) })}
            className="w-full min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-white text-lg px-4 tabular-nums focus:outline-none focus:border-sky-500"
            placeholder="60"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Chiều cao (cm)
          </label>
          <input
            type="number"
            min={30}
            value={patient.heightCm || ''}
            onChange={(e) =>
              setPatient({ heightCm: e.target.value ? Number(e.target.value) : undefined })
            }
            className="w-full min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-white text-lg px-4 tabular-nums focus:outline-none focus:border-sky-500"
            placeholder="165"
          />
        </div>
      </div>

      {bmi !== null && (
        <p className="text-sm text-slate-400">
          BMI:{' '}
          <span
            className={`font-bold tabular-nums ${
              bmi >= 40
                ? 'text-red-400'
                : bmi >= 30
                  ? 'text-amber-400'
                  : 'text-emerald-400'
            }`}
          >
            {bmi}
          </span>
          {bmi >= 40
            ? ' — Béo phì bệnh lý ⚠️'
            : bmi >= 30
              ? ' — Béo phì'
              : bmi < 18.5
                ? ' — Gầy'
                : ' — Bình thường'}
        </p>
      )}

      {/* Dị ứng */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">
          Dị ứng thuốc / chất
        </label>
        <div className="flex flex-wrap gap-2 mb-2">
          {patient.allergies.map((a) => (
            <span
              key={a}
              className="flex items-center gap-1 rounded-full bg-red-950 border border-red-700 text-red-300 text-xs px-3 py-1"
            >
              {a}
              <button
                onClick={() => removeAllergy(a)}
                className="ml-1 text-red-400 hover:text-red-200"
                aria-label={`Xóa ${a}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <input
          type="text"
          placeholder="Nhập và nhấn Enter (vd: Penicillin, Latex...)"
          className="w-full min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-white text-sm px-4 focus:outline-none focus:border-sky-500"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              addAllergy((e.target as HTMLInputElement).value)
              ;(e.target as HTMLInputElement).value = ''
            }
          }}
        />
      </div>

      {/* Thuốc đang dùng */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">
          Thuốc đang dùng
        </label>
        <div className="flex flex-wrap gap-2 mb-2">
          {patient.currentMedications.map((m) => (
            <span
              key={m}
              className="flex items-center gap-1 rounded-full bg-amber-950 border border-amber-700 text-amber-300 text-xs px-3 py-1"
            >
              {m}
              <button
                onClick={() => removeMed(m)}
                className="ml-1 text-amber-400 hover:text-amber-200"
                aria-label={`Xóa ${m}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <input
          type="text"
          placeholder="Nhập và nhấn Enter (vd: Aspirin, Warfarin...)"
          className="w-full min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-white text-sm px-4 focus:outline-none focus:border-sky-500"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              addMed((e.target as HTMLInputElement).value)
              ;(e.target as HTMLInputElement).value = ''
            }
          }}
        />
      </div>

      <Button
        variant="primary"
        size="lg"
        className="w-full"
        disabled={!isValid}
        onClick={onNext}
      >
        Tiếp theo — Chọn phẫu thuật →
      </Button>
    </div>
  )
}
