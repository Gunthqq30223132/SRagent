import { useSettingsStore } from '@/store/settingsStore'
import { Button } from '@/components/ui/Button'
import { ShieldAlert } from 'lucide-react'

export function DisclaimerModal() {
  const { disclaimerAccepted, acceptDisclaimer } = useSettingsStore()

  if (disclaimerAccepted) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="disclaimer-title"
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/70 sm:items-center"
    >
      <div className="w-full max-w-lg rounded-t-2xl sm:rounded-2xl bg-slate-800 border border-slate-600 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-7 w-7 text-amber-400 shrink-0" />
          <h2 id="disclaimer-title" className="text-lg font-bold text-white">
            Tuyên bố Miễn trừ Trách nhiệm Y tế
          </h2>
        </div>

        <div className="space-y-3 text-sm text-slate-300 leading-relaxed max-h-64 overflow-y-auto pr-1">
          <p>
            Ứng dụng <strong className="text-white">AnaesthesiaVN</strong> được xây dựng nhằm hỗ trợ
            bác sĩ gây mê hồi sức trong việc tham khảo liều thuốc và các chỉ số lâm sàng.
          </p>
          <p>
            <strong className="text-amber-400">Kết quả từ ứng dụng này KHÔNG thay thế phán đoán
            lâm sàng của bác sĩ.</strong> Mọi quyết định điều trị phải được thực hiện bởi nhân
            viên y tế có chuyên môn, dựa trên tình trạng cụ thể của từng bệnh nhân.
          </p>
          <p>
            Các công thức tính toán được tham khảo từ tài liệu y khoa chuẩn quốc tế và Dược thư
            Quốc gia Việt Nam. Tuy nhiên, người dùng phải tự xác minh tính phù hợp với phác đồ
            của cơ sở y tế mình đang công tác.
          </p>
          <p className="text-slate-400 text-xs">
            Tuân thủ Nghị định 13/2023/NĐ-CP về Bảo vệ Dữ liệu Cá nhân. Ứng dụng không thu thập
            hay lưu trữ thông tin định danh bệnh nhân.
          </p>
        </div>

        <Button
          size="lg"
          fullWidth
          onClick={acceptDisclaimer}
        >
          Tôi hiểu và đồng ý tiếp tục
        </Button>
      </div>
    </div>
  )
}
