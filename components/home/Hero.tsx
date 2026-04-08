'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search, Car, TrendingUp, Users } from 'lucide-react'

const budgetOptions = [
  { value: '', label: 'Any Budget' },
  { value: 'under5k', label: 'Under $5,000' },
  { value: '5k-15k', label: '$5,000 – $15,000' },
  { value: '15k-30k', label: '$15,000 – $30,000' },
  { value: 'over30k', label: 'Over $30,000' },
]

const typeOptions = [
  { value: '', label: 'All Types' },
  { value: 'Sedan', label: 'Sedan' },
  { value: 'SUV', label: 'SUV' },
  { value: 'Truck', label: 'Truck' },
  { value: 'Van', label: 'Van' },
  { value: 'Coupe', label: 'Coupe' },
]

const stats = [
  { icon: Car, label: '2,400+ Cars Listed' },
  { icon: TrendingUp, label: '50+ Events' },
  { icon: Users, label: '8,000+ Members' },
]

export default function Hero() {
  const router = useRouter()
  const [budget, setBudget] = useState('')
  const [carType, setCarType] = useState('')

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    const params = new URLSearchParams()
    if (budget) params.set('priceRange', budget)
    if (carType) params.set('carType', carType)
    router.push(`/cars?${params.toString()}`)
  }

  return (
    <section className="relative overflow-hidden bg-[#1A1A1A] text-white min-h-[85vh] flex items-center">
      {/* Background car image */}
      <div className="absolute inset-0">
        <img
          src="https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1600&q=80"
          alt=""
          className="w-full h-full object-cover opacity-30"
        />
      </div>
      {/* Dark gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#1A1A1A]/95 via-[#1A1A1A]/85 to-[#7A1E1E]/40" />
      {/* Gold shimmer line at top */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#CBA135] to-transparent" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 md:py-32">
        <div className="max-w-3xl mx-auto text-center">
          {/* Label */}
          <div className="inline-flex items-center gap-2 bg-[#CBA135]/10 border border-[#CBA135]/30 rounded-full px-4 py-1.5 mb-6">
            <div className="w-1.5 h-1.5 rounded-full bg-[#CBA135]" />
            <span className="text-[#CBA135] text-xs font-semibold tracking-wider uppercase">
              🇰🇭 Cambodia First
            </span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-black leading-tight mb-5 tracking-tight">
            Find Your{' '}
            <span className="text-[#CBA135]">Perfect Car</span>
            <br />
            in Cambodia
          </h1>

          {/* Subheadline */}
          <p className="text-gray-300 text-lg md:text-xl leading-relaxed mb-10 max-w-2xl mx-auto">
            Smart pricing insights, trusted listings, and a community that knows cars.
          </p>

          {/* Search Form */}
          <form
            onSubmit={handleSearch}
            className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-2 flex flex-col sm:flex-row gap-2 max-w-2xl mx-auto mb-12"
          >
            <div className="flex-1 relative">
              <select
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-white text-[#1A1A1A] text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] font-medium"
              >
                {budgetOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>

            <div className="flex-1 relative">
              <select
                value={carType}
                onChange={(e) => setCarType(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-white text-[#1A1A1A] text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] font-medium"
              >
                {typeOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>

            <button
              type="submit"
              className="flex items-center justify-center gap-2 px-6 py-3 bg-[#CBA135] text-[#1A1A1A] font-bold rounded-xl hover:bg-[#b8922e] transition-colors text-sm whitespace-nowrap"
            >
              <Search className="w-4 h-4" />
              Search Cars
            </button>
          </form>

          {/* Stats */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-8">
            {stats.map(({ icon: Icon, label }, idx) => (
              <div key={idx} className="flex items-center gap-2 text-gray-300">
                <Icon className="w-4 h-4 text-[#CBA135]" />
                <span className="text-sm font-medium">{label}</span>
                {idx < stats.length - 1 && (
                  <span className="hidden sm:block w-px h-4 bg-gray-600 ml-6" />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom wave */}
      <div className="absolute bottom-0 left-0 right-0">
        <svg viewBox="0 0 1440 60" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M0 60L1440 60L1440 0C1200 40 960 60 720 60C480 60 240 40 0 0L0 60Z" fill="#F8F5F0" />
        </svg>
      </div>
    </section>
  )
}
