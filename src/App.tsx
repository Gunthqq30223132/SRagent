import { RouterProvider } from 'react-router-dom'
import { router } from '@/router'
import { DisclaimerModal } from '@/components/layout/DisclaimerModal'

export default function App() {
  return (
    <>
      <RouterProvider router={router} />
      <DisclaimerModal />
    </>
  )
}
