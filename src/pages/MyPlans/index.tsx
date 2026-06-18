import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Trash2, ChevronRight, ClipboardList } from 'lucide-react'
import { useSavedPlansStore } from '@/store/planStore'
import { Button } from '@/components/ui/Button'
import type { SavedPlan, AnaesthesiaType } from '@/types/medical'

const ANAESTHESIA_SHORT: Record<AnaesthesiaType, string> = {
  general: 'Toàn thân',
  neuraxial: 'Tủy sống/NMC',
  regional: 'Tê vùng',
  local: 'Tê tại chỗ',
  mac: 'An thần (MAC)',
  combined: 'Kết hợp',
}

const ASA_COLOR: Record<string, string> = {
  I: 'text-emerald-400',
  II: 'text-sky-400',
  III: 'text-amber-400',
  IV: 'text-orange-400',
  V: 'text-red-400',
  VI: 'text-slate-400',
}

function PlanCard({ plan, onView, onDelete }: {
  plan: SavedPlan
  onView: () => void
  onDelete: () => void
}) {
  const date = new Date(plan.createdAt).toLocaleDateString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="rounded-xl bg-slate-800 border border-slate-700 overflow-hidden">
      <button
        onClick={onView}
        className="w-full text-left p-4 hover:bg-slate-700/50 transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-white font-semibold text-base truncate">{plan.surgeryNameVn}</p>
            <div className="flex flex-wrap items-center gap-2 mt-1.5">
              <span className="text-xs text-slate-400">{ANAESTHESIA_SHORT[plan.anaesthesiaType]}</span>
              <span className="text-slate-600">·</span>
              <span className={`text-xs font-bold ${ASA_COLOR[plan.asaClass]}`}>
                ASA {plan.asaClass}
              </span>
              <span className="text-slate-600">·</span>
              <span className="text-xs text-slate-500">{date}</span>
            </div>
          </div>
          <ChevronRight className="h-5 w-5 text-slate-500 shrink-0 mt-1" />
        </div>
      </button>
      <div className="border-t border-slate-700 px-4 py-2 flex justify-end">
        <button
          onClick={onDelete}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-red-400 transition-colors min-h-[36px] px-2"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Xóa
        </button>
      </div>
    </div>
  )
}

function PlanDetailModal({ plan, onClose }: { plan: SavedPlan; onClose: () => void }) {
  const { generatedPlan: gp } = plan.plan ? { generatedPlan: plan.plan } : { generatedPlan: null }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950 overflow-y-auto">
      <div className="sticky top-0 z-10 bg-slate-950 border-b border-slate-800 px-4 py-3 flex items-center gap-3">
        <button
          onClick={onClose}
          className="flex items-center justify-center h-10 w-10 rounded-xl bg-slate-800 border border-slate-700 text-slate-400"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <p className="text-white font-semibold text-sm">{plan.surgeryNameVn}</p>
          <p className="text-xs text-slate-400">
            {new Date(plan.createdAt).toLocaleDateString('vi-VN')}
          </p>
        </div>
      </div>

      <div className="px-4 py-6 space-y-4 max-w-lg mx-auto w-full">
        {/* Summary */}
        <div className="rounded-xl bg-slate-800 border border-slate-700 p-4">
          <div className="flex gap-6">
            <div>
              <p className="text-xs text-slate-500">Phương pháp</p>
              <p className="text-sky-300 font-semibold text-sm mt-0.5">
                {ANAESTHESIA_SHORT[plan.anaesthesiaType]}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">ASA</p>
              <p className={`font-bold text-lg ${ASA_COLOR[plan.asaClass]}`}>
                {plan.asaClass}
              </p>
            </div>
          </div>
        </div>

        {/* Warnings */}
        {gp?.warnings && gp.warnings.length > 0 && (
          <div className="space-y-2">
            {gp.warnings.map((w, i) => (
              <div key={i} className="flex gap-3 rounded-xl border border-red-600 bg-red-950/40 p-4">
                <span className="text-red-400 shrink-0">⚠️</span>
                <p className="text-red-300 text-sm leading-relaxed">{w}</p>
              </div>
            ))}
          </div>
        )}

        {/* Sections */}
        {gp?.sections?.map((section, i) => (
          <div key={i} className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
            <h3 className="text-sky-400 text-sm font-semibold mb-3">{section.title}</h3>
            <ul className="space-y-2">
              {section.items.map((item, j) => (
                <li key={j} className="flex gap-2 text-sm text-slate-300 leading-relaxed">
                  <span className="text-slate-600 tabular-nums shrink-0">{j + 1}.</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}

        <p className="text-xs text-slate-500 text-center pb-4">
          Kết quả chỉ mang tính tham khảo — không thay thế phán đoán lâm sàng
        </p>
      </div>
    </div>
  )
}

export default function MyPlans() {
  const navigate = useNavigate()
  const { savedPlans, deletePlan, clearAll } = useSavedPlansStore()
  const [viewingPlan, setViewingPlan] = useState<SavedPlan | null>(null)

  if (viewingPlan) {
    return <PlanDetailModal plan={viewingPlan} onClose={() => setViewingPlan(null)} />
  }

  return (
    <div className="px-4 py-6 max-w-lg mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/')}
          className="flex items-center justify-center h-10 w-10 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">Kế hoạch của tôi</h1>
          <p className="text-xs text-slate-400">{savedPlans.length} kế hoạch đã lưu</p>
        </div>
      </div>

      {savedPlans.length === 0 ? (
        <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4 text-center">
          <ClipboardList className="h-16 w-16 text-slate-700" />
          <div>
            <p className="text-slate-400 font-medium">Chưa có kế hoạch nào</p>
            <p className="text-slate-600 text-sm mt-1">
              Tạo kế hoạch gây mê và nhấn "Lưu kế hoạch" để xem lại ở đây
            </p>
          </div>
          <Button variant="primary" size="md" onClick={() => navigate('/ke-hoach-gay-me')}>
            Tạo kế hoạch mới
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {savedPlans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              onView={() => setViewingPlan(plan)}
              onDelete={() => deletePlan(plan.id)}
            />
          ))}

          <button
            onClick={() => {
              if (confirm('Xóa tất cả kế hoạch đã lưu?')) clearAll()
            }}
            className="w-full text-xs text-slate-600 hover:text-red-400 transition-colors min-h-[44px]"
          >
            Xóa tất cả
          </button>
        </div>
      )}
    </div>
  )
}
