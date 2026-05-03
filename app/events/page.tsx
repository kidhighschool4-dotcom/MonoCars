'use client'

import { useState, useEffect } from 'react'
import { mockEvents } from '@/lib/mockData'
import EventCard from '@/components/events/EventCard'
import { Calendar } from 'lucide-react'
import type { CarEvent } from '@/types'

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
    <div className="min-h-screen bg-[#F8F5F0]">
      {/* Header */}
      <div className="bg-[#1A1A1A] py-12 md:py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-2">
            <Calendar className="w-5 h-5 text-[#CBA135]" />
            <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider">
              Events
            </p>
          </div>
          <h1 className="text-3xl md:text-4xl font-black text-white">
            Car Events in Cambodia
          </h1>
          <p className="text-gray-400 mt-2 text-sm">
            Motor shows, car meets, racing events and group drives across the country
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Category Filter */}
        <div className="flex flex-wrap gap-2 mb-8">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                activeCategory === cat
                  ? 'bg-[#CBA135] text-[#1A1A1A]'
                  : 'bg-white text-gray-600 border border-gray-200 hover:border-[#CBA135] hover:text-[#CBA135]'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Count */}
        <p className="text-sm text-gray-500 mb-6">
          Showing{' '}
          <span className="font-semibold text-[#1A1A1A]">{filtered.length}</span>{' '}
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
