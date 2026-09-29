// Single source of truth for car search filters. Used by the home hero,
// the listings filter bar and CarsClient so the values always agree.

export const PRICE_RANGES: Record<string, { label: string; min?: number; max?: number }> = {
  'all':      { label: 'Any budget' },
  'under15k': { label: 'Under $15k', max: 15000 },
  '15k-30k':  { label: '$15k – $30k', min: 15000, max: 30000 },
  '30k-50k':  { label: '$30k – $50k', min: 30000, max: 50000 },
  'over50k':  { label: '$50k +', min: 50000 },
}

// Matches the car_types rows seeded in supabase/schema.sql
export const BODY_TYPES = [
  'Sedan',
  'SUV',
  'Pickup',
  'Hatchback',
  'MPV (Minivan)',
  'Sports',
  'Convertible',
  'Station Wagon',
] as const

export const SORT_OPTIONS = [
  { value: 'newest',      label: 'Newest' },
  { value: 'price-asc',   label: 'Price: low to high' },
  { value: 'price-desc',  label: 'Price: high to low' },
  { value: 'mileage-asc', label: 'Lowest mileage' },
] as const

export const priceOptions = Object.entries(PRICE_RANGES).map(([value, r]) => ({ value, label: r.label }))
