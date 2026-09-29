import { Suspense } from 'react'
import CarsClient, { CarGridSkeleton } from './CarsClient'

export default function CarsPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <CarGridSkeleton />
        </div>
      }
    >
      <CarsClient />
    </Suspense>
  )
}
