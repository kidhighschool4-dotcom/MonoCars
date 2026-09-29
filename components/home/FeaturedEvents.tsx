import { getFeaturedEvents } from '@/lib/db'
import EventCard from '@/components/events/EventCard'
import SectionHeading from '@/components/ui/SectionHeading'

export default async function FeaturedEvents() {
  const featured = await getFeaturedEvents(3)
  if (featured.length === 0) return null

  return (
    <section className="py-20 md:py-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="What’s on"
          title="Meet the community"
          description="Motor shows, weekend drives and car meets around Cambodia."
          action={{ href: '/events', label: 'All events' }}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 md:gap-6">
          {featured.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      </div>
    </section>
  )
}
