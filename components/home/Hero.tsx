'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Search, Sparkles, ChevronDown } from 'lucide-react'
import { BODY_TYPES, priceOptions } from '@/lib/carFilters'

const stats = [
  { value: '2,400+', label: 'Cars listed' },
  { value: '8,000+', label: 'Members' },
  { value: '50+', label: 'Events a year' },
]

function HeroSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="relative flex-1 min-w-0 block text-left px-5 py-3 rounded-2xl hover:bg-paper transition-colors cursor-pointer">
      <span className="block text-xs font-medium text-subtle">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent text-ink text-[15px] font-semibold appearance-none focus:outline-none cursor-pointer pr-6"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-5 bottom-3.5 w-4 h-4 text-subtle" />
    </label>
  )
}

export default function Hero() {
  const router = useRouter()
  const [budget, setBudget] = useState('all')
  const [carType, setCarType] = useState('all')

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    const params = new URLSearchParams()
    if (budget !== 'all') params.set('priceRange', budget)
    if (carType !== 'all') params.set('carType', carType)
    const qs = params.toString()
    router.push(qs ? `/cars?${qs}` : '/cars')
  }

  return (
    <section className="relative overflow-hidden bg-ink text-white">
      {/* Photo + gradients */}
      <div className="absolute inset-0">
        <img
          src="https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=2000&q=80"
          alt=""
          className="w-full h-full object-cover object-center opacity-60"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-ink via-ink/80 to-ink/20" />
        <div className="absolute inset-0 bg-gradient-to-t from-ink via-transparent to-ink/40" />
        <div className="absolute -bottom-40 -left-40 w-[36rem] h-[36rem] rounded-full bg-brand/25 blur-[120px]" />
      </div>

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 md:pt-28 md:pb-20">
        <div className="max-w-3xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 backdrop-blur px-3.5 py-1.5 text-sm text-white/80">
            <span className="w-1.5 h-1.5 rounded-full bg-brand" />
            Cambodia&apos;s car marketplace
          </p>

          <h1 className="mt-6 text-5xl sm:text-6xl lg:text-7xl font-semibold tracking-tight leading-[1.02]">
            Find the right car.
            <br />
            <span className="text-brand">Pay the right price.</span>
          </h1>

          <p className="mt-6 text-lg md:text-xl text-white/70 leading-relaxed max-w-xl">
            Every listing gets an AI price check, so you know if it&apos;s a good deal before you call the seller.
          </p>
          <p className="mt-2 text-white/50" lang="km">រកឡានដែលត្រូវចិត្ត ក្នុងតម្លៃសមរម្យ</p>
        </div>

        {/* Search */}
        <form
          onSubmit={handleSearch}
          className="mt-10 max-w-3xl bg-white rounded-3xl p-2 flex flex-col sm:flex-row sm:items-center gap-1 shadow-2xl shadow-black/30"
        >
          <HeroSelect label="Budget" value={budget} onChange={setBudget} options={priceOptions} />
          <div className="hidden sm:block w-px h-10 bg-line" />
          <HeroSelect
            label="Body type"
            value={carType}
            onChange={setCarType}
            options={[{ value: 'all', label: 'Any type' }, ...BODY_TYPES.map((t) => ({ value: t, label: t }))]}
          />
          <button
            type="submit"
            className="flex items-center justify-center gap-2 px-7 py-4 bg-brand text-white font-semibold rounded-2xl hover:bg-brand-strong transition-colors"
          >
            <Search className="w-5 h-5" />
            Search cars
          </button>
        </form>

        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-white/60">
          <span>Popular:</span>
          {['SUV', 'Sedan', 'Pickup'].map((t) => (
            <Link key={t} href={`/cars?carType=${encodeURIComponent(t)}`} className="text-white/90 hover:text-brand underline-offset-4 hover:underline">
              {t}
            </Link>
          ))}
          <Link href="/recommend" className="inline-flex items-center gap-1.5 text-white/90 hover:text-brand">
            <Sparkles className="w-4 h-4 text-brand" />
            Not sure? Ask the AI Advisor
          </Link>
        </div>

        {/* Stats */}
        <dl className="mt-16 md:mt-24 grid grid-cols-3 max-w-2xl border-t border-white/10">
          {stats.map((s) => (
            <div key={s.label} className="pt-6 pr-4">
              <dt className="sr-only">{s.label}</dt>
              <dd className="text-3xl md:text-4xl font-semibold tracking-tight tnum">{s.value}</dd>
              <dd className="text-sm text-white/55 mt-1">{s.label}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}
