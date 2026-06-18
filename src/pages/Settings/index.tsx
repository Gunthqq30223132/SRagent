import { Moon, Sun, Scale, Building2, Info } from 'lucide-react'
import { useSettingsStore } from '@/store/settingsStore'
import { usePatientStore } from '@/store/patientStore'

export default function SettingsPage() {
  const { theme, setTheme, weightUnit, setWeightUnit, hospitalName, setHospitalName } = useSettingsStore()
  const { reset } = usePatientStore()

  return (
    <div className="px-4 py-6 max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Cài đặt</h1>

      <section className="space-y-2">
        <p className="text-xs text-slate-400 uppercase tracking-wide px-1">Giao diện</p>
        <div className="rounded-xl bg-slate-800 border border-slate-700 divide-y divide-slate-700">
          <SettingRow icon={theme === 'dark' ? Moon : Sun} label="Giao diện">
            <ToggleChips
              options={[{ value: 'dark', label: 'Tối' }, { value: 'light', label: 'Sáng' }]}
              value={theme}
              onChange={setTheme}
            />
          </SettingRow>
          <SettingRow icon={Scale} label="Đơn vị cân nặng">
            <ToggleChips
              options={[{ value: 'kg', label: 'kg' }, { value: 'lb', label: 'lb' }]}
              value={weightUnit}
              onChange={setWeightUnit}
            />
          </SettingRow>
        </div>
      </section>

      <section className="space-y-2">
        <p className="text-xs text-slate-400 uppercase tracking-wide px-1">Cơ sở y tế</p>
        <div className="rounded-xl bg-slate-800 border border-slate-700 p-4">
          <div className="flex items-center gap-3 mb-3">
            <Building2 className="h-5 w-5 text-slate-400" />
            <label className="text-sm text-slate-300">Tên bệnh viện / phòng khám</label>
          </div>
          <input
            type="text"
            value={hospitalName}
            onChange={(e) => setHospitalName(e.target.value)}
            placeholder="Ví dụ: BV Chợ Rẫy — Khoa Gây mê"
            className="w-full rounded-lg bg-slate-700 border border-slate-600 px-3 py-3 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none min-h-[48px]"
          />
        </div>
      </section>

      <section className="space-y-2">
        <p className="text-xs text-slate-400 uppercase tracking-wide px-1">Bệnh nhân</p>
        <button
          onClick={reset}
          className="w-full rounded-xl bg-slate-800 border border-slate-700 p-4 min-h-[56px] text-left text-sm text-red-400 hover:border-red-700 transition-colors"
        >
          Xóa dữ liệu bệnh nhân hiện tại
        </button>
      </section>

      <section className="space-y-2">
        <div className="rounded-xl bg-slate-800 border border-slate-700 p-4 flex gap-3">
          <Info className="h-5 w-5 text-sky-400 shrink-0 mt-0.5" />
          <div className="text-sm text-slate-400 space-y-1">
            <p className="font-medium text-slate-200">AnaesthesiaVN v0.1.0</p>
            <p>Công cụ hỗ trợ quyết định lâm sàng gây mê cho bác sĩ Việt Nam.</p>
            <p>Tuân thủ Nghị định 13/2023/NĐ-CP về Bảo vệ Dữ liệu Cá nhân.</p>
          </div>
        </div>
      </section>
    </div>
  )
}

function SettingRow({ icon: Icon, label, children }: { icon: React.ElementType; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 p-4 min-h-[56px]">
      <div className="flex items-center gap-3">
        <Icon className="h-5 w-5 text-slate-400" />
        <span className="text-sm text-slate-300">{label}</span>
      </div>
      {children}
    </div>
  )
}

function ToggleChips<T extends string>({
  options, value, onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex gap-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium min-h-[36px] transition-colors ${
            value === opt.value
              ? 'bg-sky-500 text-white'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
