import { useEffect, useRef } from 'react'
import {
  AlertTriangle, CheckCircle2, Info, Copy, Save, RefreshCw
} from 'lucide-react'
import { usePlanStore, useSavedPlansStore } from '@/store/planStore'
import { generateAnaestheticPlan } from '@/core/planGenerator'
import { Button } from '@/components/ui/Button'
import type { PlanSection } from '@/types/medical'

const SECTION_ICON: Record<string, React.ElementType> = {
  info: Info,
  caution: AlertTriangle,
  danger: AlertTriangle,
}

const SECTION_COLOR: Record<string, string> = {
  info: 'border-sky-800 bg-sky-950/30',
  caution: 'border-amber-700 bg-amber-950/30',
  danger: 'border-red-700 bg-red-950/30',
}

const SECTION_TITLE_COLOR: Record<string, string> = {
  info: 'text-sky-400',
  caution: 'text-amber-400',
  danger: 'text-red-400',
}

function PlanSectionCard({ section }: { section: PlanSection }) {
  const level = section.level ?? 'info'
  const Icon = SECTION_ICON[level]
  return (
    <div className={`rounded-xl border p-4 ${SECTION_COLOR[level]}`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`h-4 w-4 shrink-0 ${SECTION_TITLE_COLOR[level]}`} aria-hidden />
        <h3 className={`text-sm font-semibold ${SECTION_TITLE_COLOR[level]}`}>
          {section.title}
        </h3>
      </div>
      <ul className="space-y-2">
        {section.items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-slate-300 leading-relaxed">
            <span className="text-slate-600 tabular-nums shrink-0 mt-0.5">{i + 1}.</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Step3Plan({ onBack, onReset }: { onBack: () => void; onReset: () => void }) {
  const { buildPlanInput, generatedPlan, setGeneratedPlan, surgery } = usePlanStore()
  const { savePlan } = useSavedPlansStore()
  const generated = useRef(false)

  useEffect(() => {
    if (generated.current) return
    generated.current = true
    const input = buildPlanInput()
    if (!input) return
    const plan = generateAnaestheticPlan(input)
    setGeneratedPlan(plan)
  }, [buildPlanInput, setGeneratedPlan])

  if (!generatedPlan || !surgery) {
    return (
      <div className="flex items-center justify-center min-h-[30vh]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
      </div>
    )
  }

  function copyToClipboard() {
    if (!generatedPlan) return
    const text = [
      `KẾ HOẠCH GÂY MÊ — ${surgery?.surgeryNameVn ?? ''}`,
      `Phương pháp: ${generatedPlan.anaesthesiaTypeLabel}`,
      `ASA: ${generatedPlan.asaClass}`,
      '',
      ...generatedPlan.warnings.map((w) => `⚠️ CẢNH BÁO: ${w}`),
      '',
      ...generatedPlan.sections.flatMap((s) => [
        `\n## ${s.title}`,
        ...s.items.map((item, i) => `${i + 1}. ${item}`),
      ]),
      '',
      '---',
      'Kết quả chỉ mang tính tham khảo — không thay thế phán đoán lâm sàng.',
      `Tạo lúc: ${new Date(generatedPlan.generatedAt).toLocaleString('vi-VN')}`,
    ].join('\n')
    navigator.clipboard.writeText(text).catch(() => {})
  }

  function handleSave() {
    if (!generatedPlan || !surgery) return
    const input = buildPlanInput()
    if (!input) return
    const counter = Date.now()
    savePlan({
      id: String(counter),
      label: `${surgery.surgeryNameVn}`,
      createdAt: counter,
      surgeryNameVn: surgery.surgeryNameVn,
      anaesthesiaType: generatedPlan.anaesthesiaType,
      asaClass: generatedPlan.asaClass,
      input,
      plan: generatedPlan,
    })
  }

  const asaColors: Record<string, string> = {
    I: 'text-emerald-400',
    II: 'text-sky-400',
    III: 'text-amber-400',
    IV: 'text-orange-400',
    V: 'text-red-400',
    VI: 'text-slate-400',
  }

  return (
    <div className="space-y-5">
      {/* Header summary */}
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-4">
        <h2 className="text-white font-bold text-lg">{surgery.surgeryNameVn}</h2>
        <p className="text-slate-400 text-xs mt-0.5">{surgery.surgeryNameEn}</p>
        <div className="flex flex-wrap gap-3 mt-3">
          <div>
            <p className="text-xs text-slate-500">Phương pháp</p>
            <p className="text-sky-300 font-semibold text-sm">{generatedPlan.anaesthesiaTypeLabel}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">ASA</p>
            <p className={`font-bold text-lg tabular-nums ${asaColors[generatedPlan.asaClass] ?? 'text-white'}`}>
              {generatedPlan.asaClass}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Thời gian</p>
            <p className="text-white text-sm">{surgery.durationMin}–{surgery.durationMax} phút</p>
          </div>
        </div>
      </div>

      {/* Warnings */}
      {generatedPlan.warnings.length > 0 && (
        <div className="space-y-2">
          {generatedPlan.warnings.map((w, i) => (
            <div
              key={i}
              className="flex gap-3 rounded-xl border border-red-600 bg-red-950/40 p-4"
            >
              <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" aria-hidden />
              <p className="text-red-300 text-sm font-medium leading-relaxed">{w}</p>
            </div>
          ))}
        </div>
      )}

      {/* AI notice */}
      <div className="flex items-center gap-2 rounded-xl bg-slate-800/60 border border-slate-700 px-4 py-3">
        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
        <p className="text-xs text-slate-400">
          Kế hoạch dựa trên quy tắc lâm sàng · Hỗ trợ AI sẽ có trong phiên bản tiếp theo
        </p>
      </div>

      {/* Plan sections */}
      <div className="space-y-4">
        {generatedPlan.sections.map((section, i) => (
          <PlanSectionCard key={i} section={section} />
        ))}
      </div>

      {/* Disclaimer */}
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 px-4 py-3">
        <p className="text-xs text-slate-500 leading-relaxed">
          ⚕️ Kết quả chỉ mang tính tham khảo và hỗ trợ quyết định lâm sàng. Bác sĩ gây mê
          có trách nhiệm đánh giá và điều chỉnh theo tình trạng cụ thể của bệnh nhân. Không
          thay thế phán đoán lâm sàng chuyên môn.
        </p>
      </div>

      {/* Action buttons */}
      <div className="grid grid-cols-2 gap-3">
        <Button variant="outline" size="md" onClick={copyToClipboard} className="flex items-center gap-2 justify-center">
          <Copy className="h-4 w-4" />
          Sao chép
        </Button>
        <Button variant="outline" size="md" onClick={handleSave} className="flex items-center gap-2 justify-center">
          <Save className="h-4 w-4" />
          Lưu kế hoạch
        </Button>
      </div>
      <div className="flex gap-3">
        <Button variant="ghost" size="md" onClick={onBack} className="flex-1">
          ← Sửa thông tin
        </Button>
        <Button variant="primary" size="md" onClick={onReset} className="flex-1 flex items-center gap-2 justify-center">
          <RefreshCw className="h-4 w-4" />
          Kế hoạch mới
        </Button>
      </div>
    </div>
  )
}
