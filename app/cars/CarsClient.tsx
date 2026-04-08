'use client'

import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import CarCard from '@/components/cars/CarCard'
import CarFilters, { FilterState } from '@/components/cars/CarFilters'
import type { Car } from '@/types'
import Link from 'next/link'
import { Sparkles } from 'lucide-react'

const PRICE_RANGES: Record<string, { min?: number; max?: number }> = {
  'all':      {},
  'under10k': { max: 10000 },
  '10k-30k':  { min: 10000, max: 30000 },
  '30k-60k':  { min: 30000, max: 60000 },
  'over60k':  { min: 60000 },
}

export default function CarsClient() {
  const searchParams = useSearchParams()

  const [filters, setFilters] = useState<FilterState>({
    priceRange: searchParams.get('priceRange') || 'all',
    carType:    searchParams.get('carType')    || 'all',
    sortBy:     'newest',
  })
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
      params.set('sort', filters.sortBy)
      params.set('limit', '60')

      const res  = await fetch(`/api/cars?${params}`)
      const data = await res.json()
      setCars(data.cars ?? [])
    } catch {
      setError('Failed to load listings. Please refresh.')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => { fetchCars() }, [fetchCars])

  return (
    <div className="min-h-screen bg-[#F8F5F0]">
      {/* Page Header */}
      <div className="bg-[#1A1A1A] py-12 md:py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider mb-2">Browse</p>
          <h1 className="text-3xl md:text-4xl font-black text-white">Car Listings</h1>
          <p className="text-gray-400 mt-2 text-sm">
            Discover verified car listings across Cambodia with smart price analysis
          </p>
          <Link
            href="/recommend"
            className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-[#CBA135] text-[#1A1A1A] text-sm font-semibold rounded-xl hover:bg-[#b8922e] transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            Try AI Car Advisor
          </Link>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Filters */}
        <div className="mb-6">
          <CarFilters filters={filters} onChange={setFilters} />
        </div>

        {/* Count */}
        {!loading && !error && (
          <div className="flex items-center justify-between mb-6">
            <p className="text-sm text-gray-500">
              Showing <span className="font-semibold text-[#1A1A1A]">{cars.length}</span>{' '}
              {cars.length === 1 ? 'car' : 'cars'}
            </p>
          </div>
        )}

        {/* States */}
        {error && (
          <div className="text-center py-16 text-red-500 text-sm">{error}</div>
        )}

        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="bg-white rounded-2xl overflow-hidden animate-pulse">
                <div className="aspect-video bg-gray-200" />
                <div className="p-4 space-y-3">
                  <div className="h-4 bg-gray-200 rounded w-3/4" />
                  <div className="h-6 bg-gray-200 rounded w-1/2" />
                  <div className="h-3 bg-gray-200 rounded w-full" />
                  <div className="h-9 bg-gray-200 rounded-xl" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && !error && cars.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {cars.map((car) => (
              <CarCard key={car.id} car={car} />
            ))}
          </div>
        )}

        {!loading && !error && cars.length === 0 && (
          <div className="text-center py-20">
            <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="font-semibold text-[#1A1A1A] mb-1">No cars found</h3>
            <p className="text-gray-500 text-sm">Try adjusting your filters</p>
          </div>
        )}
      </div>
    </div>
  )
}
