'use client'

import { useState, useRef, useEffect } from 'react'
import Link from 'next/link'
import { Send, Sparkles, RotateCcw, MapPin, Gauge, Car } from 'lucide-react'
import type { Car as CarType } from '@/types'
import Badge from '@/components/ui/Badge'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Message {
  role: 'user' | 'assistant'
  content: string
  cars?: CarType[]
  suggestions?: string[]
}

// ─── Suggestion detection ─────────────────────────────────────────────────────

const SUGGESTION_SETS: { keywords: string[]; options: string[] }[] = [
  {
    keywords: ['budget', 'how much', 'price range', 'spend', 'afford'],
    options: ['Under $15,000', '$15,000 – $30,000', '$30,000 – $60,000', '$60,000 – $100,000', 'Over $100,000'],
  },
  {
    keywords: ['use', 'plan to use', 'purpose', 'primarily', 'mainly', 'looking for it'],
    options: ['Daily city commute', 'Family road trips', 'Business meetings', 'Off-road / province travel', 'Mixed use'],
  },
  {
    keywords: ['body type', 'type of car', 'prefer', 'suv or', 'sedan or', 'pickup', 'style of car'],
    options: ['SUV', 'Sedan', 'Pickup Truck', 'Hatchback', 'No preference'],
  },
  {
    keywords: ['fuel', 'petrol', 'diesel', 'electric', 'hybrid', 'engine type'],
    options: ['Gasoline', 'Diesel', 'Hybrid', 'Electric', 'No preference'],
  },
  {
    keywords: ['seat', 'passenger', 'family size', 'how many people', 'how many seats', 'occupant'],
    options: ['2 seats (just me)', '5 seats (small family)', '7 seats (large family)'],
  },
  {
    keywords: ['new or used', 'how old', 'year', 'age of', 'mileage preference'],
    options: ['Brand new (0–2 years)', 'Nearly new (2–5 years)', 'Used (5+ years, best value)'],
  },
]

function getSuggestions(aiMessage: string): string[] {
  const lower = aiMessage.toLowerCase()
  for (const set of SUGGESTION_SETS) {
    if (set.keywords.some((kw) => lower.includes(kw))) {
      return set.options
    }
  }
  return []
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-4 py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-[#CBA135] animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  )
}

function SearchingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-[#CBA135] font-medium px-1 py-2">
      <div className="w-4 h-4 border-2 border-[#CBA135] border-t-transparent rounded-full animate-spin" />
      Searching database...
    </div>
  )
}

function CarResultCard({ car }: { car: CarType }) {
  return (
    <Link href={`/cars/${car.id}`} className="block group">
      <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200">
        <div className="relative aspect-video overflow-hidden bg-gray-100">
          <img
            src={car.images[0]}
            alt={`${car.year} ${car.make} ${car.model}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
          <div className="absolute top-2 left-2">
            <Badge label={car.priceLabel} size="sm" />
          </div>
        </div>
        <div className="p-4">
          <h3 className="font-bold text-[#1A1A1A] text-sm mb-1">
            {car.year} {car.make} {car.model}
          </h3>
          <p className="text-xl font-black text-[#CBA135] mb-2">
            ${car.price.toLocaleString()}
          </p>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <Car className="w-3 h-3" /> {car.type}
            </span>
            <span className="flex items-center gap-1">
              <Gauge className="w-3 h-3" /> {car.mileage.toLocaleString()}km
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="w-3 h-3" /> {car.location}
            </span>
          </div>
        </div>
      </div>
    </Link>
  )
}

// ─── Main Page ───────────────────────────────────────────────────────────────

const INITIAL_MESSAGE: Message = {
  role: 'assistant',
  content: "Hi! I'm your MonoCars AI advisor 🚗\n\nI'll help you find the perfect car in Cambodia. Let's start — what's your budget range in USD?",
  suggestions: ['Under $15,000', '$15,000 – $30,000', '$30,000 – $60,000', '$60,000 – $100,000', 'Over $100,000'],
}

export default function RecommendPage() {
  const [messages, setMessages]   = useState<Message[]>([INITIAL_MESSAGE])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [searching, setSearching] = useState(false)
  const bottomRef  = useRef<HTMLDivElement>(null)
  const inputRef   = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const reset = () => {
    setMessages([INITIAL_MESSAGE])
    setInput('')
    setLoading(false)
    setSearching(false)
    inputRef.current?.focus()
  }

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    const userMsg: Message = { role: 'user', content: trimmed }
    const history = [...messages, userMsg]
    setMessages(history)
    setInput('')
    setLoading(true)
    setSearching(false)

    const apiMessages = history.map(({ role, content }) => ({ role, content }))

    try {
      const response = await fetch('/api/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: apiMessages }),
      })

      if (!response.body) throw new Error('No response body')

      const reader  = response.body.getReader()
      const decoder = new TextDecoder()
      let aiText    = ''
      let carResults: CarType[] = []

      // Placeholder for streaming assistant message
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const lines = decoder.decode(value).split('\n').filter((l) => l.startsWith('data: '))

        for (const line of lines) {
          try {
            const event = JSON.parse(line.slice(6))

            if (event.type === 'text') {
              aiText += event.content
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { role: 'assistant', content: aiText }
                return next
              })
            }

            if (event.type === 'searching') {
              setSearching(true)
            }

            if (event.type === 'cars') {
              carResults = event.cars
              setSearching(false)
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { role: 'assistant', content: aiText, cars: carResults }
                return next
              })
            }

            if (event.type === 'done') {
              // Attach suggestions based on what AI just asked
              const suggestions = getSuggestions(aiText)
              setMessages((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last.role === 'assistant' && !last.cars) {
                  next[next.length - 1] = { ...last, suggestions }
                }
                return next
              })
              setLoading(false)
            }

            if (event.type === 'error') {
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { role: 'assistant', content: event.message ?? 'Something went wrong.' }
                return next
              })
              setLoading(false)
            }
          } catch {
            // skip malformed lines
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: 'Connection error. Please try again.' }
        return next
      })
    } finally {
      setLoading(false)
      setSearching(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
  }

  const isLastAssistant = (idx: number) =>
    idx === messages.length - 1 && messages[idx].role === 'assistant'

  return (
    <div className="min-h-screen bg-[#F8F5F0] flex flex-col">

      {/* Header */}
      <div className="bg-[#1A1A1A] py-8 md:py-12">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-[#CBA135] flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-[#1A1A1A]" />
            </div>
            <div>
              <p className="text-[#CBA135] text-xs font-semibold uppercase tracking-widest">AI-Powered</p>
              <h1 className="text-2xl font-black text-white">Car Advisor</h1>
            </div>
          </div>
          <p className="text-gray-400 text-sm">
            Answer a few questions and our AI will find your perfect car from Cambodia's best listings.
          </p>
        </div>
      </div>

      {/* Chat */}
      <div className="flex-1 max-w-3xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-5">

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className="max-w-[85%] w-full">

              {/* AI avatar label */}
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-7 h-7 rounded-full bg-[#CBA135] flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-3.5 h-3.5 text-[#1A1A1A]" />
                  </div>
                  <span className="text-xs font-semibold text-gray-500">MonoCars AI</span>
                </div>
              )}

              {/* Bubble */}
              <div
                className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-[#1A1A1A] text-white rounded-tr-sm ml-auto w-fit'
                    : 'bg-white border border-gray-100 text-[#1A1A1A] shadow-sm rounded-tl-sm'
                }`}
              >
                {msg.content || (loading && isLastAssistant(idx) ? <TypingDots /> : null)}
              </div>

              {/* Searching indicator */}
              {msg.role === 'assistant' && searching && isLastAssistant(idx) && (
                <div className="mt-2 ml-1">
                  <SearchingIndicator />
                </div>
              )}

              {/* Quick-reply suggestion buttons */}
              {msg.role === 'assistant' && msg.suggestions && msg.suggestions.length > 0 && !loading && isLastAssistant(idx) && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {msg.suggestions.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => send(opt)}
                      className="px-3.5 py-2 rounded-xl text-sm font-medium border-2 border-[#CBA135] text-[#1A1A1A] bg-white hover:bg-[#CBA135] transition-colors duration-150"
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}

              {/* Car results */}
              {msg.cars && msg.cars.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    Top Matches ({msg.cars.length})
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {msg.cars.slice(0, 6).map((car) => (
                      <CarResultCard key={car.id} car={car} />
                    ))}
                  </div>
                  <div className="mt-4 flex gap-2">
                    <Link
                      href="/cars"
                      className="flex-1 text-center py-2.5 text-sm font-semibold border border-gray-200 rounded-xl text-gray-600 hover:bg-gray-50 transition-colors"
                    >
                      Browse All Listings
                    </Link>
                    <button
                      onClick={reset}
                      className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold bg-[#CBA135] text-[#1A1A1A] rounded-xl hover:bg-[#b8922e] transition-colors"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      New Search
                    </button>
                  </div>
                </div>
              )}

            </div>
          </div>
        ))}

        {/* Loading typing bubble */}
        {loading && messages[messages.length - 1]?.content === '' && !searching && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm shadow-sm">
              <TypingDots />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="sticky bottom-0 bg-white/95 backdrop-blur-md border-t border-gray-100 px-4 sm:px-6 py-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-3">
            <button
              onClick={reset}
              title="Start over"
              className="p-2.5 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors flex-shrink-0"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Or type your own answer..."
              disabled={loading}
              className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5 text-sm text-[#1A1A1A] placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135] disabled:opacity-50"
            />
            <button
              onClick={() => send(input)}
              disabled={loading || !input.trim()}
              className="p-2.5 rounded-xl bg-[#CBA135] text-[#1A1A1A] hover:bg-[#b8922e] disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-xs text-gray-400 text-center mt-2">
            Tap a button or type your own answer · Enter to send
          </p>
        </div>
      </div>
    </div>
  )
}
