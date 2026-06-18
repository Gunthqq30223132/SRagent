import { WifiOff } from 'lucide-react'
import { useOffline } from '@/hooks/useOffline'

export function OfflineIndicator() {
  const isOffline = useOffline()
  if (!isOffline) return null

  return (
    <div
      role="status"
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-amber-700 px-4 py-2 text-sm font-medium text-amber-100"
    >
      <WifiOff className="h-4 w-4 shrink-0" />
      <span>Đang offline — Tính toán vẫn hoạt động · Tính năng AI không khả dụng</span>
    </div>
  )
}
