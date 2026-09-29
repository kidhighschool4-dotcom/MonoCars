import { mockCars, mockEvents, mockPosts } from '@/lib/mockData'
import type { Car, CarEvent, Post } from '@/types'
import type { CarFilters } from '@/lib/db'

// Preview mode: set MONOCARS_MOCK_DATA=1 to serve lib/mockData.ts instead of Supabase.
// Lets the UI run locally without database credentials.
export const USE_MOCK_DATA = process.env.MONOCARS_MOCK_DATA === '1'

export function mockGetCars(filters: CarFilters = {}): Car[] {
  let cars = mockCars.filter((c) =>
    (!filters.priceMin || c.price >= filters.priceMin) &&
    (!filters.priceMax || c.price <= filters.priceMax) &&
    (!filters.seats || (c.seats ?? 5) >= filters.seats) &&
    (!filters.type || filters.type === 'all' || c.type === filters.type) &&
    (!filters.fuel || filters.fuel === 'all' || c.fuel === filters.fuel)
  )

  const sorters: Record<string, (a: Car, b: Car) => number> = {
    'newest':      (a, b) => b.createdAt.localeCompare(a.createdAt),
    'price-asc':   (a, b) => a.price - b.price,
    'price-desc':  (a, b) => b.price - a.price,
    'mileage-asc': (a, b) => a.mileage - b.mileage,
  }
  cars = [...cars].sort(sorters[filters.sortBy ?? 'newest'] ?? sorters['newest'])

  const start = filters.offset ?? 0
  return cars.slice(start, filters.limit ? start + filters.limit : undefined)
}

export function mockGetCar(id: string): Car | null {
  return mockCars.find((c) => c.id === id) ?? null
}

export function mockGetRelatedCars(carId: string, type: string, limit: number): Car[] {
  if (!type) return []
  return mockCars.filter((c) => c.id !== carId && c.type === type).slice(0, limit)
}

export function mockGetCarsByIds(ids: string[]): Car[] {
  return ids.map((id) => mockGetCar(id)).filter(Boolean) as Car[]
}

export function mockGetEvents(limit?: number): CarEvent[] {
  const events = [...mockEvents].sort((a, b) => a.date.localeCompare(b.date))
  return limit ? events.slice(0, limit) : events
}

export function mockGetEvent(id: string): CarEvent | null {
  return mockEvents.find((e) => e.id === id) ?? null
}

export function mockGetPosts(limit: number): Post[] {
  return mockPosts.slice(0, limit)
}
