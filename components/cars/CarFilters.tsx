'use client'

import clsx from 'clsx'
import { ChevronDown } from 'lucide-react'
import { BODY_TYPES, SORT_OPTIONS, priceOptions } from '@/lib/carFilters'

export interface FilterState {
  priceRange: string
  carType: string
  sortBy: string
}

interface CarFiltersProps {
  filters: FilterState
  onChange: (filters: FilterState) => void
}

function PillSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: readonly { value: string; label: string }[]
}) {
  return (
    <label className="relative inline-flex items-center">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none bg-surface border border-line rounded-full pl-4 pr-10 py-2.5 text-sm font-medium text-ink hover:border-ink focus:outline-none focus:border-brand transition-colors cursor-pointer"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3.5 w-4 h-4 text-muted" />
    </label>
  )
}

export default function CarFilters({ filters, onChange }: CarFiltersProps) {
  const set = (key: keyof FilterState, value: string) => onChange({ ...filters, [key]: value })
  const types = ['all', ...BODY_TYPES]

  return (
    <div className="space-y-4">
      {/* Body type chips — scroll sideways on small screens */}
      <div className="-mx-4 px-4 sm:mx-0 sm:px-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex gap-2 w-max">
          {types.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => set('carType', t)}
              aria-pressed={filters.carType === t}
              className={clsx(
                'px-4 py-2.5 rounded-full text-sm font-medium border transition-colors whitespace-nowrap',
                filters.carType === t
                  ? 'bg-ink text-white border-ink'
                  : 'bg-surface text-ink border-line hover:border-ink'
              )}
            >
              {t === 'all' ? 'All types' : t}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <PillSelect label="Budget" value={filters.priceRange} onChange={(v) => set('priceRange', v)} options={priceOptions} />
        <PillSelect label="Sort by" value={filters.sortBy} onChange={(v) => set('sortBy', v)} options={SORT_OPTIONS} />
        {(filters.priceRange !== 'all' || filters.carType !== 'all') && (
          <button
            type="button"
            onClick={() => onChange({ ...filters, priceRange: 'all', carType: 'all' })}
            className="px-3 py-2.5 text-sm font-medium text-brand hover:underline underline-offset-4"
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  )
}
