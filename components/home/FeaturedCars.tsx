import Link from 'next/link'
import { getFeaturedCars } from '@/lib/db'
import CarCard from '@/components/cars/CarCard'
import SectionHeading from '@/components/ui/SectionHeading'

export default async function FeaturedCars() {
  const featured = await getFeaturedCars(6)

  return (
    <section className="py-20 md:py-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="Fresh on FBM"
          title="Latest cars for sale"
          description="Hand-picked listings from across Cambodia, each with an AI price check."
          action={{ href: '/cars', label: 'View all cars' }}
        />

        {featured.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 md:gap-6">
            {featured.map((car) => (
              <CarCard key={car.id} car={car} />
            ))}
          </div>
        ) : (
          <div className="text-center py-16 rounded-3xl border border-dashed border-line text-muted">
            No listings yet.{' '}
            <Link href="/submit" className="text-brand font-semibold hover:underline">List the first car</Link>
          </div>
        )}
      </div>
    </section>
  )
}
