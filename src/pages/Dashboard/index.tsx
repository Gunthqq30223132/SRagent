import { useNavigate } from 'react-router-dom'
import {
  Pill, Activity, Droplets, Wind, Brain,
  MessageSquare, ChevronRight, Stethoscope, ClipboardList, BookOpen
} from 'lucide-react'
import { usePatientStore } from '@/store/patientStore'
import { clsx } from 'clsx'

interface ToolCard {
  label: string
  sublabel: string
  icon: React.ElementType
  to: string
  color: string
}

const TIER1_TOOLS: ToolCard[] = [
  {
    label: 'Kế hoạch Gây mê',
    sublabel: 'Wizard 3 bước · Phẫu thuật + Bệnh kèm → Kế hoạch',
    icon: ClipboardList,
    to: '/ke-hoach-gay-me',
    color: 'text-teal-400 bg-teal-950 border-teal-800',
  },
  {
    label: 'Tính liều khởi mê',
    sublabel: 'Propofol · Ketamin · Etomidate',
    icon: Pill,
    to: '/tinh-lieu/khoi-me',
    color: 'text-sky-400 bg-sky-950 border-sky-800',
  },
  {
    label: 'Thuốc giãn cơ',
    sublabel: 'Rocuronium · Vecuronium · Succinylcholine',
    icon: Activity,
    to: '/tinh-lieu/gian-co',
    color: 'text-violet-400 bg-violet-950 border-violet-800',
  },
  {
    label: 'Dịch truyền',
    sublabel: 'Công thức 4-2-1 · Bù thiếu hụt',
    icon: Droplets,
    to: '/may-tinh/dich-truyen',
    color: 'text-cyan-400 bg-cyan-950 border-cyan-800',
  },
  {
    label: 'MAC thuốc bốc hơi',
    sublabel: 'Sevoflurane · Isoflurane · Desflurane',
    icon: Wind,
    to: '/tinh-lieu/mac',
    color: 'text-emerald-400 bg-emerald-950 border-emerald-800',
  },
]

const TIER2_TOOLS: ToolCard[] = [
  {
    label: 'Kế hoạch của tôi',
    sublabel: 'Xem lại kế hoạch gây mê đã lưu',
    icon: BookOpen,
    to: '/ke-hoach-cua-toi',
    color: 'text-indigo-400 bg-indigo-950 border-indigo-800',
  },
  {
    label: 'Phân loại ASA',
    sublabel: 'Đánh giá tình trạng thể chất trước mổ',
    icon: Stethoscope,
    to: '/tinh-diem/asa',
    color: 'text-amber-400 bg-amber-950 border-amber-800',
  },
  {
    label: 'Tư vấn AI',
    sublabel: 'Trả lời câu hỏi lâm sàng · Sắp ra mắt',
    icon: MessageSquare,
    to: '/tu-van-ai',
    color: 'text-slate-400 bg-slate-800 border-slate-700',
  },
  {
    label: 'Điểm Glasgow (GCS)',
    sublabel: 'Đánh giá ý thức',
    icon: Brain,
    to: '/tinh-diem/glasgow',
    color: 'text-pink-400 bg-pink-950 border-pink-800',
  },
]

function ToolButton({ label, sublabel, icon: Icon, to, color }: ToolCard) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(to)}
      className={clsx(
        'flex w-full items-center gap-4 rounded-xl border p-4',
        'min-h-[72px] text-left transition-opacity active:opacity-70',
        color,
      )}
    >
      <div className="shrink-0 rounded-lg p-2">
        <Icon className="h-6 w-6" aria-hidden />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-white text-base leading-tight">{label}</p>
        <p className="text-xs text-slate-400 mt-0.5 truncate">{sublabel}</p>
      </div>
      <ChevronRight className="h-5 w-5 text-slate-500 shrink-0" aria-hidden />
    </button>
  )
}

export default function Dashboard() {
  const { patient } = usePatientStore()

  return (
    <div className="px-4 py-6 space-y-6 max-w-lg mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">AnaesthesiaVN</h1>
        <p className="text-slate-400 text-sm mt-1">Hỗ trợ Quyết định Lâm sàng Gây mê</p>
      </div>

      {/* Patient context */}
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-4">
        <p className="text-xs text-slate-400 uppercase tracking-wide mb-2">Bệnh nhân hiện tại</p>
        <div className="flex flex-wrap gap-3 text-sm">
          <span className="text-white font-medium">{patient.weightKg} kg</span>
          <span className="text-slate-500">·</span>
          <span className="text-white font-medium">{patient.ageYears} tuổi</span>
          {patient.heightCm && (
            <>
              <span className="text-slate-500">·</span>
              <span className="text-white font-medium">{patient.heightCm} cm</span>
            </>
          )}
          {patient.asaScore && (
            <>
              <span className="text-slate-500">·</span>
              <span className="text-amber-400 font-semibold">ASA {patient.asaScore}</span>
            </>
          )}
        </div>
      </div>

      {/* Công cụ ưu tiên cao */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Dùng trong phòng mổ
        </h2>
        <div className="space-y-3">
          {TIER1_TOOLS.map((tool) => (
            <ToolButton key={tool.to} {...tool} />
          ))}
        </div>
      </section>

      {/* Công cụ bổ sung */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Đánh giá & Hỗ trợ
        </h2>
        <div className="space-y-3">
          {TIER2_TOOLS.map((tool) => (
            <ToolButton key={tool.to} {...tool} />
          ))}
        </div>
      </section>

      <p className="text-center text-xs text-slate-600 pb-2">
        Kết quả chỉ mang tính tham khảo — không thay thế phán đoán lâm sàng
      </p>
    </div>
  )
}
