'use client'

import { useState, useEffect } from 'react'
import { mockEvents } from '@/lib/mockData'
import EventCard from '@/components/events/EventCard'
import type { CarEvent } from '@/types'
import PageHeader from '@/components/ui/PageHeader'

const categories = ['All', 'Motor Show', 'Car Meet', 'Racing', 'EV Show', 'Group Drive', 'Off-Road']

export default function EventsPage() {
  const [activeCategory, setActiveCategory] = useState('All')
  const [events, setEvents] = useState<CarEvent[]>(mockEvents)

  useEffect(() => {
    fetch('/api/events')
      .then((r) => r.json())
      .then(({ events: dbEvents }) => {
        if (dbEvents?.length) setEvents(dbEvents)
      })
      .catch(() => {})
  }, [])

  const filtered = activeCategory === 'All'
    ? events
    : events.filter((e) => e.category === activeCategory)

  return (
    <div className="min-h-screen bg-paper">
      <PageHeader
        eyebrow="Events"
        title="Car events in Cambodia"
        description="Motor shows, car meets, races and weekend drives around the country."
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Category Filter */}
        <div className="flex flex-wrap gap-2 mb-8">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                activeCategory === cat
                  ? 'bg-brand text-white'
                  : 'bg-white text-muted border border-line hover:border-brand hover:text-brand'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Count */}
        <p className="text-sm text-muted mb-6">
          Showing{' '}
          <span className="font-semibold text-ink">{filtered.length}</span>{' '}
          event{filtered.length !== 1 ? 's' : ''}
        </p>

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      </div>
    </div>
  )
}
