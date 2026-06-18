import { Outlet } from 'react-router-dom'
import { NavigationBar } from './NavigationBar'
import { OfflineIndicator } from './OfflineIndicator'

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-900 text-slate-100">
      <OfflineIndicator />
      <main className="flex-1 overflow-y-auto pb-20 pt-safe">
        <Outlet />
      </main>
      <NavigationBar />
    </div>
  )
}
