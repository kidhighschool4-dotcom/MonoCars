'use client'

import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Sparkles, SearchX, Search } from 'lucide-react'
import CarCard from '@/components/cars/CarCard'
import CarFilters, { FilterState } from '@/components/cars/CarFilters'
import { PRICE_RANGES } from '@/lib/carFilters'
import type { Car } from '@/types'

export function CarGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-surface rounded-2xl border border-line overflow-hidden animate-pulse">
          <div className="aspect-[4/3] bg-paper" />
          <div className="p-5 space-y-3">
            <div className="h-5 bg-paper rounded-full w-2/3" />
            <div className="h-4 bg-paper rounded-full w-1/2" />
            <div className="h-7 bg-paper rounded-full w-1/3 mt-6" />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function CarsClient() {
  const searchParams = useSearchParams()

  const initialRange = searchParams.get('priceRange') ?? 'all'
  const [filters, setFilters] = useState<FilterState>({
    priceRange: initialRange in PRICE_RANGES ? initialRange : 'all',
    carType:    searchParams.get('carType') || 'all',
    sortBy:     'newest',
  })
  const [query, setQuery]     = useState(searchParams.get('q') ?? '')
  const [draft, setDraft]     = useState(query)
  const [cars, setCars]       = useState<Car[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  const fetchCars = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      const range = PRICE_RANGES[filters.priceRange] ?? {}
      if (range.min) params.set('priceMin', String(range.min))
      if (range.max) params.set('priceMax', String(range.max))
      if (filters.carType !== 'all') params.set('type', filters.carType)
      if (query.trim()) params.set('q', query.trim())
      params.set('sort', filters.sortBy)
      params.set('limit', '60')

      const res  = await fetch(`/api/cars?${params}`)
      const data = await res.json()
      setCars(data.cars ?? [])
    } catch {
      setError('Couldn’t load listings. Please refresh the page.')
    } finally {
      setLoading(false)
    }
  }, [filters, query])

  useEffect(() => { fetchCars() }, [fetchCars])

  return (
    <div className="min-h-screen">
      {/* Page header */}
      <div className="bg-surface border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-12 pb-8 md:pt-16">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-8">
            <div>
              <p className="inline-flex items-center gap-2 text-sm font-medium text-muted mb-3">
                <span className="w-1.5 h-1.5 rounded-full bg-brand" />
                Buy a car
              </p>
              <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink">Cars for sale in Cambodia</h1>
            </div>
            <Link
              href="/recommend"
              className="self-start md:self-auto inline-flex items-center gap-2 px-5 py-3 rounded-full bg-brand-soft text-brand text-sm font-semibold hover:bg-brand hover:text-white transition-colors"
            >
              <Sparkles className="w-4 h-4" />
              Help me choose
            </Link>
          </div>
          <form
            role="search"
            onSubmit={(e) => { e.preventDefault(); setQuery(draft) }}
            className="mb-4 flex items-center gap-2 max-w-2xl"
          >
            <label className="relative flex-1">
              <span className="sr-only">Search cars</span>
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted" />
              <input
                type="search"
                name="q"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Search make, model or place — e.g. Camry ភ្នំពេញ"
                className="w-full rounded-full border border-line bg-surface pl-12 pr-4 py-3 text-[15px] text-ink placeholder:text-subtle focus:outline-none focus:border-brand"
              />
            </label>
            <button type="submit" className="px-5 py-3 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors">
              Search
            </button>
          </form>
          <CarFilters filters={filters} onChange={setFilters} />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-10">
        {!loading && !error && (
          <p className="text-sm text-muted mb-6" aria-live="polite" data-testid={cars.length ? 'results-count' : 'results-empty'}>
            <span className="font-semibold text-ink tnum">{cars.length}</span> {cars.length === 1 ? 'car' : 'cars'} found
          </p>
        )}

        {error && <div className="text-center py-16 text-rose-600">{error}</div>}

        {loading && <CarGridSkeleton />}

        {!loading && !error && cars.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {cars.map((car) => (
              <CarCard key={car.id} car={car} />
            ))}
          </div>
        )}

        {!loading && !error && cars.length === 0 && (
          <div className="text-center py-20 rounded-3xl border border-dashed border-line bg-surface">
            <div className="w-14 h-14 rounded-full bg-paper flex items-center justify-center mx-auto mb-4">
              <SearchX className="w-6 h-6 text-muted" />
            </div>
            <h3 className="text-lg font-semibold text-ink mb-1">No cars match those filters</h3>
            <p className="text-muted mb-6">Try a different budget or body type.</p>
            <button
              onClick={() => setFilters({ ...filters, priceRange: 'all', carType: 'all' })}
              className="px-5 py-2.5 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors"
            >
              Show all cars
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
