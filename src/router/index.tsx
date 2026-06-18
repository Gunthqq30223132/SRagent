import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'

const Dashboard        = lazy(() => import('@/pages/Dashboard'))
const DrugDosing       = lazy(() => import('@/pages/calculators/DrugDosing'))
const ASAScore         = lazy(() => import('@/pages/calculators/ASAScore'))
const FluidCalc        = lazy(() => import('@/pages/calculators/FluidCalc'))
const MACCalc          = lazy(() => import('@/pages/calculators/MACCalc'))
const MuscleRelaxant   = lazy(() => import('@/pages/calculators/MuscleRelaxant'))
const AIConsult        = lazy(() => import('@/pages/AIConsult'))
const Settings         = lazy(() => import('@/pages/Settings'))
const AnaestheticPlan  = lazy(() => import('@/pages/AnaestheticPlan'))
const MyPlans          = lazy(() => import('@/pages/MyPlans'))

function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
    </div>
  )
}

function Wrap({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Loading />}>{children}</Suspense>
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true,                   element: <Wrap><Dashboard /></Wrap> },
      { path: 'tinh-lieu/khoi-me',     element: <Wrap><DrugDosing /></Wrap> },
      { path: 'tinh-lieu/gian-co',     element: <Wrap><MuscleRelaxant /></Wrap> },
      { path: 'tinh-lieu/mac',         element: <Wrap><MACCalc /></Wrap> },
      { path: 'tinh-diem/asa',         element: <Wrap><ASAScore /></Wrap> },
      { path: 'may-tinh/dich-truyen',  element: <Wrap><FluidCalc /></Wrap> },
      { path: 'tu-van-ai',             element: <Wrap><AIConsult /></Wrap> },
      { path: 'cai-dat',               element: <Wrap><Settings /></Wrap> },
      { path: 'ke-hoach-gay-me',       element: <Wrap><AnaestheticPlan /></Wrap> },
      { path: 'ke-hoach-cua-toi',      element: <Wrap><MyPlans /></Wrap> },
    ],
  },
])
