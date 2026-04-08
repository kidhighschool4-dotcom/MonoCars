import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { mockEvents } from '@/lib/mockData'
import EventCard from '@/components/events/EventCard'

export default function FeaturedEvents() {
  const featured = mockEvents.slice(0, 3)

  return (
    <section className="py-16 md:py-20 bg-[#F0EDE6]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="flex items-end justify-between mb-10">
          <div>
            <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider mb-2">
              What&apos;s Happening
            </p>
            <h2 className="text-3xl md:text-4xl font-black text-[#1A1A1A]">
              Upcoming Events
            </h2>
          </div>
          <Link
            href="/events"
            className="hidden sm:flex items-center gap-1.5 text-sm font-semibold text-[#CBA135] hover:gap-2.5 transition-all"
          >
            View All Events
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {featured.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>

        {/* Mobile CTA */}
        <div className="mt-8 text-center sm:hidden">
          <Link
            href="/events"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[#1A1A1A] text-white font-semibold rounded-xl hover:bg-[#CBA135] hover:text-[#1A1A1A] transition-all duration-200"
          >
            View All Events
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  )
}
