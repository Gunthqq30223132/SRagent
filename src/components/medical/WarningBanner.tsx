import { clsx } from 'clsx'
import { AlertTriangle, Info, XCircle, CheckCircle } from 'lucide-react'

type Level = 'info' | 'success' | 'caution' | 'danger'

interface WarningBannerProps {
  level?: Level
  message: string
  className?: string
}

const config: Record<Level, { bg: string; text: string; icon: React.ElementType }> = {
  info:    { bg: 'bg-slate-700',  text: 'text-slate-200',  icon: Info },
  success: { bg: 'bg-green-900',  text: 'text-green-300',  icon: CheckCircle },
  caution: { bg: 'bg-amber-900',  text: 'text-amber-300',  icon: AlertTriangle },
  danger:  { bg: 'bg-red-900',    text: 'text-red-300',    icon: XCircle },
}

export function WarningBanner({ level = 'info', message, className }: WarningBannerProps) {
  const { bg, text, icon: Icon } = config[level]

  return (
    <div
      role="alert"
      className={clsx(
        'flex items-start gap-3 rounded-lg p-3',
        bg,
        text,
        className,
      )}
    >
      <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
      <p className="text-sm leading-relaxed">{message}</p>
    </div>
  )
}
