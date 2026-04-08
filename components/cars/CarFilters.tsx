'use client'

import { SlidersHorizontal } from 'lucide-react'

export interface FilterState {
  priceRange: string
  carType: string
  sortBy: string
}

interface CarFiltersProps {
  filters: FilterState
  onChange: (filters: FilterState) => void
}

const priceOptions = [
  { value: 'all', label: 'Any Budget' },
  { value: 'under5k', label: 'Under $5,000' },
  { value: '5k-15k', label: '$5,000 – $15,000' },
  { value: '15k-30k', label: '$15,000 – $30,000' },
  { value: 'over30k', label: 'Over $30,000' },
]

const typeOptions = [
  { value: 'all', label: 'All Types' },
  { value: 'Sedan', label: 'Sedan' },
  { value: 'SUV', label: 'SUV' },
  { value: 'Truck', label: 'Truck' },
  { value: 'Hatchback', label: 'Hatchback' },
  { value: 'Van', label: 'Van' },
  { value: 'Coupe', label: 'Coupe' },
]

const sortOptions = [
  { value: 'newest', label: 'Newest First' },
  { value: 'price-asc', label: 'Price: Low to High' },
  { value: 'price-desc', label: 'Price: High to Low' },
  { value: 'mileage-asc', label: 'Mileage: Low to High' },
]

export default function CarFilters({ filters, onChange }: CarFiltersProps) {
  const handleChange = (key: keyof FilterState, value: string) => {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
      <div className="flex items-center gap-2 mb-4">
        <SlidersHorizontal className="w-4 h-4 text-[#CBA135]" />
        <span className="font-semibold text-sm text-[#1A1A1A]">Filter &amp; Sort</span>
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Price Range */}
        <div className="flex-1 relative">
          <select
            value={filters.priceRange}
            onChange={(e) => handleChange('priceRange', e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm text-[#1A1A1A] bg-white appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135] hover:border-gray-300 transition-all"
          >
            {priceOptions.map((opt) => (
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

        {/* Car Type */}
        <div className="flex-1 relative">
          <select
            value={filters.carType}
            onChange={(e) => handleChange('carType', e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm text-[#1A1A1A] bg-white appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135] hover:border-gray-300 transition-all"
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

        {/* Sort By */}
        <div className="flex-1 relative">
          <select
            value={filters.sortBy}
            onChange={(e) => handleChange('sortBy', e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm text-[#1A1A1A] bg-white appearance-none focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135] hover:border-gray-300 transition-all"
          >
            {sortOptions.map((opt) => (
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
      </div>
    </div>
  )
}
