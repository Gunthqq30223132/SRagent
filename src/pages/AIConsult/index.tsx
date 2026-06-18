import { MessageSquareOff } from 'lucide-react'

export default function AIConsultPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] px-6 text-center gap-4">
      <MessageSquareOff className="h-14 w-14 text-slate-600" />
      <h1 className="text-xl font-bold text-white">Tư vấn AI</h1>
      <p className="text-slate-400 text-sm max-w-xs">
        Tính năng trả lời câu hỏi lâm sàng bằng AI đang được phát triển và sẽ ra mắt trong phiên bản tiếp theo.
      </p>
      <p className="text-slate-600 text-xs">
        Kiến trúc đã sẵn sàng để tích hợp Claude API hoặc OpenAI.
      </p>
    </div>
  )
}
