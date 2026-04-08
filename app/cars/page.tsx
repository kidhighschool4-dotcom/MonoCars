import { Suspense } from 'react'
import CarsClient from './CarsClient'

export default function CarsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#F8F5F0] flex items-center justify-center">
          <div className="text-gray-500">Loading listings...</div>
        </div>
      }
    >
      <CarsClient />
    </Suspense>
  )
}
