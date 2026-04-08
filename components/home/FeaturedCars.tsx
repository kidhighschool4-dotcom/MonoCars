import Link from 'next/link'
import { ArrowRight, Sparkles } from 'lucide-react'
import { getFeaturedCars } from '@/lib/db'
import CarCard from '@/components/cars/CarCard'

export default async function FeaturedCars() {
  const featured = await getFeaturedCars(6)

  return (
    <section className="py-16 md:py-20 bg-[#F8F5F0]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="flex items-end justify-between mb-10">
          <div>
            <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider mb-2">
              Latest Listings
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-[#1A1A1A]">Featured Cars</h2>
          </div>
          <div className="hidden sm:flex items-center gap-3">
            <Link
              href="/recommend"
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-semibold text-[#1A1A1A] bg-[#CBA135] rounded-lg hover:bg-[#b8922e] transition-colors"
            >
              <Sparkles className="w-4 h-4" />
              AI Advisor
            </Link>
            <Link
              href="/cars"
              className="flex items-center gap-1.5 text-sm font-semibold text-[#CBA135] hover:gap-2.5 transition-all"
            >
              View All Cars
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Grid */}
        {featured.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {featured.map((car) => (
              <CarCard key={car.id} car={car} />
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-gray-400 text-sm">
            No listings yet.{' '}
            <Link href="/submit" className="text-[#CBA135] hover:underline">Submit the first one.</Link>
          </div>
        )}

        {/* Mobile CTAs */}
        <div className="mt-8 flex gap-3 sm:hidden">
          <Link
            href="/recommend"
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-[#CBA135] text-[#1A1A1A] font-semibold rounded-xl text-sm"
          >
            <Sparkles className="w-4 h-4" /> AI Advisor
          </Link>
          <Link
            href="/cars"
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-[#1A1A1A] text-white font-semibold rounded-xl text-sm"
          >
            View All <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  )
}
