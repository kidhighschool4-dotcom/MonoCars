import Link from 'next/link'
import { Calendar, MapPin, Users } from 'lucide-react'
import type { CarEvent } from '@/types'

interface EventCardProps {
  event: CarEvent
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleDateString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

const categoryColors: Record<string, string> = {
  'Motor Show': 'bg-purple-100 text-purple-800',
  'Car Meet': 'bg-blue-100 text-blue-800',
  'Racing': 'bg-red-100 text-red-800',
  'EV Show': 'bg-emerald-100 text-emerald-800',
  'Group Drive': 'bg-amber-100 text-amber-800',
  'Off-Road': 'bg-orange-100 text-orange-800',
}

export default function EventCard({ event }: EventCardProps) {
  const categoryColor = categoryColors[event.category] || 'bg-gray-100 text-gray-800'

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden group hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
      {/* Image */}
      <div className="relative aspect-video overflow-hidden bg-gray-100">
        <img
          src={event.image}
          alt={event.title}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        />
        <div className="absolute top-3 left-3">
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${categoryColor}`}>
            {event.category}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-5">
        <h3 className="font-bold text-[#1A1A1A] text-base mb-3 leading-snug line-clamp-2">
          {event.title}
        </h3>

        <div className="space-y-2 mb-4">
          <div className="flex items-start gap-2 text-sm text-gray-500">
            <Calendar className="w-4 h-4 text-[#CBA135] flex-shrink-0 mt-0.5" />
            <span>{formatDate(event.date)}</span>
          </div>
          <div className="flex items-start gap-2 text-sm text-gray-500">
            <MapPin className="w-4 h-4 text-[#CBA135] flex-shrink-0 mt-0.5" />
            <span className="line-clamp-1">{event.location}</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Users className="w-4 h-4 text-[#CBA135] flex-shrink-0" />
            <span>{event.attendees.toLocaleString()} attending</span>
          </div>
        </div>

        <Link
          href={`/events/${event.id}`}
          className="block w-full text-center py-2.5 px-4 bg-[#1A1A1A] text-white text-sm font-semibold rounded-xl hover:bg-[#CBA135] hover:text-[#1A1A1A] transition-all duration-200"
        >
          View Details
        </Link>
      </div>
    </div>
  )
}
