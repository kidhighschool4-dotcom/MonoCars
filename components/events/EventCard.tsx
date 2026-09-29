import Link from 'next/link'
import { MapPin, Users } from 'lucide-react'
import type { CarEvent } from '@/types'
import SafeImage from '@/components/ui/SafeImage'

interface EventCardProps {
  event: CarEvent
}

export default function EventCard({ event }: EventCardProps) {
  const date = new Date(event.date)
  const month = date.toLocaleDateString('en-US', { month: 'short' })
  const day = date.getDate()
  const weekday = date.toLocaleDateString('en-US', { weekday: 'long' })

  return (
    <Link
      href={`/events/${event.id}`}
      className="group block bg-surface rounded-2xl border border-line overflow-hidden hover:border-brand-tint hover:shadow-[0_12px_40px_-12px_rgba(20,34,79,0.18)] transition-all duration-300"
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-paper">
        <SafeImage
          src={event.image}
          alt={event.title}
          loading="lazy"
          className="w-full h-full object-cover group-hover:scale-[1.04] transition-transform duration-500"
        />
        <span className="absolute top-3 left-3 text-xs font-semibold px-2.5 py-1 rounded-full bg-white/95 text-ink">
          {event.category}
        </span>
        {/* Date tile */}
        <div className="absolute bottom-3 left-3 w-14 rounded-xl bg-white text-center overflow-hidden shadow-lg">
          <p className="bg-brand text-white text-[11px] font-semibold uppercase py-0.5">{month}</p>
          <p className="text-xl font-bold text-ink py-1 tnum">{day}</p>
        </div>
      </div>

      <div className="p-5">
        <p className="text-sm text-muted">{weekday}</p>
        <h3 className="mt-1 font-semibold text-ink text-lg leading-snug line-clamp-2 group-hover:text-brand transition-colors">
          {event.title}
        </h3>
        <div className="mt-4 pt-4 border-t border-line flex items-center justify-between gap-3 text-sm text-muted">
          <span className="flex items-center gap-1.5 min-w-0">
            <MapPin className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">{event.location}</span>
          </span>
          <span className="flex items-center gap-1.5 flex-shrink-0 tnum">
            <Users className="w-4 h-4" />
            {event.attendees.toLocaleString()}
          </span>
        </div>
      </div>
    </Link>
  )
}
