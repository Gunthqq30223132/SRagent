import { useState, useEffect } from 'react'
import { Search, CheckCircle2, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import { usePlanStore } from '@/store/planStore'
import { Button } from '@/components/ui/Button'
import type { SelectedSurgery, SelectedComorbidity, AnaesthesiaType } from '@/types/medical'

interface SurgeryRaw {
  id: string
  nameVn: string
  nameEn: string
  anaesthesiaOptions: AnaesthesiaType[]
  recommendedAnaesthesia: AnaesthesiaType
  position: string
  durationMin: number
  durationMax: number
  urgency: 'elective' | 'urgent' | 'emergency'
  bloodLoss: 'minimal' | 'low' | 'moderate' | 'high' | 'massive'
  painLevel: 'mild' | 'moderate' | 'severe'
  airwayDifficulty: 'standard' | 'shared' | 'difficult' | 'secured'
  considerations: string[]
}

interface SpecialtyRaw {
  id: string
  nameVn: string
  icon: string
  surgeries: SurgeryRaw[]
}

interface ComorbiditiesRaw {
  id: string
  nameVn: string
  nameEn: string
  asaMinimum: string
  anaesthesiaConsiderations: string[]
  drugCautions: string[]
  monitoringNeeds: string[]
  preOpChecklist: string[]
}

interface ComorbidCategoryRaw {
  id: string
  nameVn: string
  conditions: ComorbiditiesRaw[]
}

const URGENCY_LABEL = {
  elective: 'Chương trình',
  urgent: 'Khẩn',
  emergency: 'Cấp cứu',
}

const BLOOD_LOSS_LABEL = {
  minimal: 'Rất ít',
  low: 'Ít',
  moderate: 'Vừa',
  high: 'Nhiều',
  massive: 'Rất nhiều',
}

export function Step2Surgery({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { surgery, setSurgery, comorbidities, toggleComorbidity, isEmergency, setIsEmergency } =
    usePlanStore()

  const [specialties, setSpecialties] = useState<SpecialtyRaw[]>([])
  const [comorbidCategories, setComorbidCategories] = useState<ComorbidCategoryRaw[]>([])
  const [surgerySearch, setSurgerySearch] = useState('')
  const [expandedSpecialty, setExpandedSpecialty] = useState<string | null>(null)
  const [expandedComorbid, setExpandedComorbid] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'surgery' | 'comorbid'>('surgery')

  useEffect(() => {
    fetch('/data/surgeries.json')
      .then((r) => r.json())
      .then((d) => setSpecialties(d.specialties ?? []))
      .catch(() => setSpecialties([]))

    fetch('/data/comorbidities.json')
      .then((r) => r.json())
      .then((d) => setComorbidCategories(d.categories ?? []))
      .catch(() => setComorbidCategories([]))
  }, [])

  const filteredSpecialties = surgerySearch.trim()
    ? specialties
        .map((sp) => ({
          ...sp,
          surgeries: sp.surgeries.filter(
            (s) =>
              s.nameVn.toLowerCase().includes(surgerySearch.toLowerCase()) ||
              s.nameEn.toLowerCase().includes(surgerySearch.toLowerCase()),
          ),
        }))
        .filter((sp) => sp.surgeries.length > 0)
    : specialties

  function selectSurgery(sp: SpecialtyRaw, s: SurgeryRaw) {
    const selected: SelectedSurgery = {
      specialtyId: sp.id,
      specialtyNameVn: sp.nameVn,
      surgeryId: s.id,
      surgeryNameVn: s.nameVn,
      surgeryNameEn: s.nameEn,
      anaesthesiaOptions: s.anaesthesiaOptions,
      recommendedAnaesthesia: s.recommendedAnaesthesia,
      position: s.position,
      durationMin: s.durationMin,
      durationMax: s.durationMax,
      urgency: s.urgency,
      bloodLoss: s.bloodLoss,
      painLevel: s.painLevel,
      airwayDifficulty: s.airwayDifficulty,
      considerations: s.considerations,
    }
    setSurgery(selected)
    setSurgerySearch('')
  }

  function handleComorbidToggle(cat: ComorbidCategoryRaw, cond: ComorbiditiesRaw) {
    const item: SelectedComorbidity = {
      categoryId: cat.id,
      categoryNameVn: cat.nameVn,
      conditionId: cond.id,
      conditionNameVn: cond.nameVn,
      conditionNameEn: cond.nameEn,
      asaMinimum: cond.asaMinimum as SelectedComorbidity['asaMinimum'],
      anaesthesiaConsiderations: cond.anaesthesiaConsiderations,
      drugCautions: cond.drugCautions,
      monitoringNeeds: cond.monitoringNeeds,
      preOpChecklist: cond.preOpChecklist,
    }
    toggleComorbidity(item)
  }

  const isConditionSelected = (id: string) =>
    comorbidities.some((c) => c.conditionId === id)

  return (
    <div className="space-y-5">
      {/* Tabs */}
      <div className="flex rounded-xl bg-slate-800 p-1 gap-1">
        {(['surgery', 'comorbid'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 min-h-[40px] rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-sky-600 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab === 'surgery'
              ? `Phẫu thuật${surgery ? ' ✓' : ''}`
              : `Bệnh kèm${comorbidities.length > 0 ? ` (${comorbidities.length})` : ''}`}
          </button>
        ))}
      </div>

      {/* Tab: Surgery */}
      {activeTab === 'surgery' && (
        <div className="space-y-4">
          {/* Selected display */}
          {surgery && (
            <div className="rounded-xl bg-sky-950 border border-sky-700 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs text-sky-400 font-medium mb-0.5">{surgery.specialtyNameVn}</p>
                  <p className="text-white font-semibold">{surgery.surgeryNameVn}</p>
                  <p className="text-xs text-slate-400 mt-1">{surgery.surgeryNameEn}</p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <span className="text-xs bg-slate-800 text-slate-300 rounded-full px-2 py-0.5">
                      {surgery.durationMin}–{surgery.durationMax} phút
                    </span>
                    <span className="text-xs bg-slate-800 text-slate-300 rounded-full px-2 py-0.5">
                      Mất máu: {BLOOD_LOSS_LABEL[surgery.bloodLoss]}
                    </span>
                    <span className={`text-xs rounded-full px-2 py-0.5 ${
                      surgery.urgency === 'emergency'
                        ? 'bg-red-950 text-red-300'
                        : surgery.urgency === 'urgent'
                          ? 'bg-amber-950 text-amber-300'
                          : 'bg-slate-800 text-slate-300'
                    }`}>
                      {URGENCY_LABEL[surgery.urgency]}
                    </span>
                  </div>
                </div>
                <CheckCircle2 className="h-5 w-5 text-sky-400 shrink-0 mt-1" />
              </div>
            </div>
          )}

          {/* Emergency toggle */}
          <div className="flex items-center gap-3 rounded-xl bg-slate-800 border border-slate-700 p-4">
            <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-white">Phẫu thuật cấp cứu (E)</p>
              <p className="text-xs text-slate-400">Kích hoạt protocol RSI và dạ dày đầy</p>
            </div>
            <button
              onClick={() => setIsEmergency(!isEmergency)}
              className={`relative w-12 h-6 rounded-full transition-colors ${
                isEmergency ? 'bg-red-600' : 'bg-slate-700'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  isEmergency ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={surgerySearch}
              onChange={(e) => {
                setSurgerySearch(e.target.value)
                setExpandedSpecialty(null)
              }}
              placeholder="Tìm phẫu thuật..."
              className="w-full min-h-[48px] rounded-xl bg-slate-800 border border-slate-700 text-white pl-10 pr-4 text-sm focus:outline-none focus:border-sky-500"
            />
          </div>

          {/* Surgery list */}
          <div className="space-y-2 max-h-[50vh] overflow-y-auto">
            {filteredSpecialties.length === 0 && (
              <p className="text-center text-slate-500 text-sm py-8">Không tìm thấy phẫu thuật</p>
            )}
            {filteredSpecialties.map((sp) => (
              <div key={sp.id}>
                <button
                  onClick={() =>
                    setExpandedSpecialty(expandedSpecialty === sp.id ? null : sp.id)
                  }
                  className="w-full flex items-center justify-between rounded-xl bg-slate-800 border border-slate-700 px-4 py-3 text-left hover:border-slate-500"
                >
                  <span className="text-sm font-semibold text-slate-200">{sp.nameVn}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{sp.surgeries.length}</span>
                    {expandedSpecialty === sp.id ? (
                      <ChevronDown className="h-4 w-4 text-slate-500" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-500" />
                    )}
                  </div>
                </button>

                {(expandedSpecialty === sp.id || surgerySearch.trim()) && (
                  <div className="ml-4 mt-1 space-y-1">
                    {sp.surgeries.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => selectSurgery(sp, s)}
                        className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${
                          surgery?.surgeryId === s.id
                            ? 'bg-sky-950 border-sky-600 text-sky-200'
                            : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500'
                        }`}
                      >
                        <p className="text-sm font-medium">{s.nameVn}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{s.nameEn}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Comorbidities */}
      {activeTab === 'comorbid' && (
        <div className="space-y-4">
          {comorbidities.length > 0 && (
            <div className="rounded-xl bg-slate-800 border border-slate-700 p-3">
              <p className="text-xs text-slate-400 mb-2 font-medium">Đã chọn:</p>
              <div className="flex flex-wrap gap-2">
                {comorbidities.map((c) => (
                  <span
                    key={c.conditionId}
                    className="flex items-center gap-1 rounded-full bg-violet-950 border border-violet-700 text-violet-300 text-xs px-3 py-1"
                  >
                    {c.conditionNameVn}
                    <button
                      onClick={() => toggleComorbidity(c)}
                      className="ml-1 hover:text-violet-100"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2 max-h-[55vh] overflow-y-auto">
            {comorbidCategories.map((cat) => (
              <div key={cat.id}>
                <button
                  onClick={() =>
                    setExpandedComorbid(expandedComorbid === cat.id ? null : cat.id)
                  }
                  className="w-full flex items-center justify-between rounded-xl bg-slate-800 border border-slate-700 px-4 py-3 text-left hover:border-slate-500"
                >
                  <span className="text-sm font-semibold text-slate-200">{cat.nameVn}</span>
                  <div className="flex items-center gap-2">
                    {cat.conditions.some((c) => isConditionSelected(c.id)) && (
                      <span className="h-2 w-2 rounded-full bg-violet-400" />
                    )}
                    {expandedComorbid === cat.id ? (
                      <ChevronDown className="h-4 w-4 text-slate-500" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-500" />
                    )}
                  </div>
                </button>

                {expandedComorbid === cat.id && (
                  <div className="ml-4 mt-1 space-y-1">
                    {cat.conditions.map((cond) => {
                      const selected = isConditionSelected(cond.id)
                      return (
                        <button
                          key={cond.id}
                          onClick={() => handleComorbidToggle(cat, cond)}
                          className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${
                            selected
                              ? 'bg-violet-950 border-violet-600 text-violet-200'
                              : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-medium">{cond.nameVn}</p>
                            <span className={`text-xs rounded-full px-2 py-0.5 ${
                              cond.asaMinimum >= 'IV'
                                ? 'bg-red-950 text-red-400'
                                : cond.asaMinimum >= 'III'
                                  ? 'bg-amber-950 text-amber-400'
                                  : 'bg-slate-800 text-slate-400'
                            }`}>
                              ASA ≥{cond.asaMinimum}
                            </span>
                          </div>
                          {selected && cond.drugCautions.length > 0 && (
                            <p className="text-xs text-amber-400 mt-1">
                              ⚠️ Thận trọng: {cond.drugCautions.slice(0, 2).join(', ')}
                            </p>
                          )}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3 pt-2">
        <Button variant="ghost" size="md" onClick={onBack} className="flex-1">
          ← Quay lại
        </Button>
        <Button
          variant="primary"
          size="md"
          onClick={onNext}
          disabled={!surgery}
          className="flex-1"
        >
          Tạo kế hoạch →
        </Button>
      </div>
    </div>
  )
}
