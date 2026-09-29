import { notFound } from 'next/navigation'
import Link from 'next/link'
import { Calendar, MapPin, Users, ArrowLeft, Tag } from 'lucide-react'
import { getEvent, getFeaturedEvents } from '@/lib/db'
import { mockEvents } from '@/lib/mockData'

interface PageProps {
  params: Promise<{ id: string }>
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function formatTime(dateString: string) {
  return new Date(dateString).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default async function EventDetailPage({ params }: PageProps) {
  const { id } = await params

  // Try DB first, fall back to mock (covers old integer IDs during transition)
  let event = await getEvent(id)
  if (!event) {
    const mock = mockEvents.find((e) => e.id === id)
    if (!mock) notFound()
    event = mock
  }

  const dbRelated = await getFeaturedEvents(3)
  const related = (dbRelated.length ? dbRelated : mockEvents)
    .filter((e) => e.id !== event!.id)
    .slice(0, 2)

  return (
    <div className="min-h-screen bg-paper">
      {/* Back nav */}
      <div className="bg-white border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <Link
            href="/events"
            className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Events
          </Link>
        </div>
      </div>

      {/* Hero Image */}
      <div className="relative h-64 md:h-96 overflow-hidden">
        <img
          src={event.image}
          alt={event.title}
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-ink/80 via-transparent to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 p-8">
          <div className="max-w-7xl mx-auto">
            <span className="inline-block text-xs font-semibold px-3 py-1 bg-brand text-white rounded-full mb-3">
              {event.category}
            </span>
            <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-white">{event.title}</h1>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-2xl shadow-sm border border-line p-6 mb-6">
              <h2 className="font-bold text-ink text-xl mb-4">About This Event</h2>
              <p className="text-muted leading-relaxed">{event.description}</p>
            </div>

            {/* Details */}
            <div className="bg-white rounded-2xl shadow-sm border border-line p-6">
              <h2 className="font-bold text-ink text-xl mb-5">Event Details</h2>
              <div className="space-y-4">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-brand-soft flex items-center justify-center flex-shrink-0">
                    <Calendar className="w-5 h-5 text-brand" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">Date &amp; Time</p>
                    <p className="font-semibold text-ink">{formatDate(event.date)}</p>
                    <p className="text-sm text-muted">{formatTime(event.date)}</p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-brand-soft flex items-center justify-center flex-shrink-0">
                    <MapPin className="w-5 h-5 text-brand" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">Location</p>
                    <p className="font-semibold text-ink">{event.location}</p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-brand-soft flex items-center justify-center flex-shrink-0">
                    <Users className="w-5 h-5 text-brand" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">Attendees</p>
                    <p className="font-semibold text-ink">
                      {event.attendees.toLocaleString()} people attending
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-brand-soft flex items-center justify-center flex-shrink-0">
                    <Tag className="w-5 h-5 text-brand" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">Category</p>
                    <p className="font-semibold text-ink">{event.category}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* RSVP Card */}
            <div className="bg-ink rounded-2xl p-6 text-white">
              <h3 className="font-bold text-lg mb-2">Register for this Event</h3>
              <p className="text-gray-400 text-sm mb-5">
                Join {event.attendees.toLocaleString()} others at this event.
              </p>
              <div className="flex items-center gap-3 mb-5">
                <div className="flex -space-x-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className="w-8 h-8 rounded-full border-2 border-ink bg-gradient-to-br from-brand to-brand-deep flex items-center justify-center"
                    >
                      <span className="text-white text-xs font-bold">{i}</span>
                    </div>
                  ))}
                </div>
                <span className="text-sm text-gray-400">+{(event.attendees - 4).toLocaleString()} others</span>
              </div>
              <button className="w-full py-3 bg-brand text-white font-bold rounded-xl hover:bg-brand-strong transition-colors text-sm">
                RSVP / Register
              </button>
            </div>

            {/* Share */}
            <div className="bg-white rounded-2xl shadow-sm border border-line p-6">
              <h3 className="font-semibold text-ink mb-3">Share Event</h3>
              <div className="flex gap-2">
                <button className="flex-1 py-2 bg-blue-50 text-blue-700 text-sm font-medium rounded-xl hover:bg-blue-100 transition-colors">
                  Facebook
                </button>
                <button className="flex-1 py-2 bg-sky-50 text-sky-700 text-sm font-medium rounded-xl hover:bg-sky-100 transition-colors">
                  Twitter
                </button>
                <button className="flex-1 py-2 bg-green-50 text-green-700 text-sm font-medium rounded-xl hover:bg-green-100 transition-colors">
                  WhatsApp
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Related Events */}
        {related.length > 0 && (
          <section className="mt-12">
            <h2 className="text-2xl font-semibold tracking-tight text-ink mb-6">More Events</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {related.map((e) => (
                <div key={e.id} className="bg-white rounded-2xl shadow-sm border border-line overflow-hidden flex gap-4 p-4 hover:shadow-md transition-all">
                  <div className="w-24 h-20 rounded-xl overflow-hidden flex-shrink-0">
                    <img src={e.image} alt={e.title} className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-sm text-ink truncate mb-1">{e.title}</h3>
                    <p className="text-xs text-gray-400 mb-2">{formatDate(e.date)}</p>
                    <Link
                      href={`/events/${e.id}`}
                      className="text-xs font-semibold text-brand hover:underline"
                    >
                      View Event →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
