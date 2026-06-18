import { NavLink } from 'react-router-dom'
import { LayoutGrid, ClipboardList, Calculator, BookOpen, Settings } from 'lucide-react'
import { clsx } from 'clsx'

const navItems = [
  { to: '/',                   label: 'Trang chủ', icon: LayoutGrid },
  { to: '/ke-hoach-gay-me',    label: 'Kế hoạch',  icon: ClipboardList },
  { to: '/tinh-lieu/khoi-me',  label: 'Tính liều', icon: Calculator },
  { to: '/ke-hoach-cua-toi',   label: 'Đã lưu',    icon: BookOpen },
  { to: '/cai-dat',            label: 'Cài đặt',   icon: Settings },
]

export function NavigationBar() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-slate-700 bg-slate-900">
      <ul className="flex h-16 items-center justify-around">
        {navItems.map(({ to, label, icon: Icon }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-xs font-medium transition-colors',
                  isActive ? 'text-sky-400' : 'text-slate-400 hover:text-slate-200',
                )
              }
            >
              <Icon className="h-5 w-5" aria-hidden />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
