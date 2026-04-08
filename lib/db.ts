import { supabaseAdmin } from '@/lib/supabase-server'
import type { Car } from '@/types'

// ─── Types returned by Supabase joins ───────────────────────────────────────

interface DbCarRow {
  id: string
  title: string
  model: string
  year: number
  price_usd: number
  estimated_value_usd: number
  price_label: string
  mileage_km: number
  color: string | null
  engine_cc: number | null
  seats: number
  location: string
  description: string
  source: string
  is_featured: boolean
  seller_name: string
  seller_phone: string
  created_at: string
  brands: { name: string }
  car_types: { name: string }
  fuel_types: { name: string }
  transmissions: { name: string }
  car_images: { url: string; is_primary: boolean; display_order: number }[]
  car_features: { feature: string; is_pro: boolean }[]
}

// ─── Transform DB row → app Car type ────────────────────────────────────────

function toAppCar(row: DbCarRow): Car {
  const images = [...(row.car_images ?? [])]
    .sort((a, b) => a.display_order - b.display_order)
    .map((i) => i.url)

  const pros = (row.car_features ?? [])
    .filter((f) => f.is_pro)
    .map((f) => f.feature)

  const cons = (row.car_features ?? [])
    .filter((f) => !f.is_pro)
    .map((f) => f.feature)

  return {
    id: row.id,
    make: row.brands?.name ?? '',
    model: row.model,
    year: row.year,
    price: row.price_usd,
    estimatedValue: row.estimated_value_usd,
    priceLabel: row.price_label as Car['priceLabel'],
    type: row.car_types?.name as Car['type'],
    mileage: row.mileage_km,
    location: row.location,
    images: images.length ? images : ['https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800'],
    description: row.description,
    pros,
    cons,
    sellerName: row.seller_name,
    sellerPhone: row.seller_phone,
    source: row.source as Car['source'],
    createdAt: row.created_at,
    // Extra fields from DB
    fuel: row.fuel_types?.name,
    transmission: row.transmissions?.name,
    color: row.color ?? undefined,
    seats: row.seats,
    engineCc: row.engine_cc ?? undefined,
  }
}

const CAR_SELECT = `
  id, title, model, year, price_usd, estimated_value_usd, price_label,
  mileage_km, color, engine_cc, seats, location, description, source,
  is_featured, seller_name, seller_phone, created_at,
  brands(name),
  car_types(name),
  fuel_types(name),
  transmissions(name),
  car_images(url, is_primary, display_order),
  car_features(feature, is_pro)
`

// ─── Query helpers ───────────────────────────────────────────────────────────

export interface CarFilters {
  priceMin?: number
  priceMax?: number
  type?: string
  fuel?: string
  seats?: number
  location?: string
  sortBy?: 'newest' | 'price-asc' | 'price-desc' | 'mileage-asc'
  limit?: number
  offset?: number
}

export async function getCars(filters: CarFilters = {}): Promise<Car[]> {
  let query = supabaseAdmin
    .from('cars')
    .select(CAR_SELECT)
    .eq('is_available', true)

  if (filters.priceMin) query = query.gte('price_usd', filters.priceMin)
  if (filters.priceMax) query = query.lte('price_usd', filters.priceMax)
  if (filters.seats)    query = query.gte('seats', filters.seats)

  if (filters.type && filters.type !== 'all') {
    const { data: typeRow } = await supabaseAdmin
      .from('car_types')
      .select('id')
      .eq('name', filters.type)
      .single()
    if (typeRow) query = query.eq('car_type_id', typeRow.id)
  }

  if (filters.fuel && filters.fuel !== 'all') {
    const { data: fuelRow } = await supabaseAdmin
      .from('fuel_types')
      .select('id')
      .eq('name', filters.fuel)
      .single()
    if (fuelRow) query = query.eq('fuel_type_id', fuelRow.id)
  }

  const sortMap: Record<string, { column: string; ascending: boolean }> = {
    'newest':     { column: 'created_at',  ascending: false },
    'price-asc':  { column: 'price_usd',   ascending: true  },
    'price-desc': { column: 'price_usd',   ascending: false },
    'mileage-asc':{ column: 'mileage_km',  ascending: true  },
  }
  const sort = sortMap[filters.sortBy ?? 'newest'] ?? sortMap['newest']
  query = query.order(sort.column, { ascending: sort.ascending })

  if (filters.limit)  query = query.limit(filters.limit)
  if (filters.offset) query = query.range(filters.offset, filters.offset + (filters.limit ?? 20) - 1)

  const { data, error } = await query
  if (error) { console.error('[db.getCars]', error); return [] }

  return (data as unknown as DbCarRow[]).map(toAppCar)
}

export async function getCar(id: string): Promise<Car | null> {
  const { data, error } = await supabaseAdmin
    .from('cars')
    .select(CAR_SELECT)
    .eq('id', id)
    .eq('is_available', true)
    .single()

  if (error || !data) return null
  return toAppCar(data as unknown as DbCarRow)
}

export async function getFeaturedCars(limit = 6): Promise<Car[]> {
  const { data, error } = await supabaseAdmin
    .from('cars')
    .select(CAR_SELECT)
    .eq('is_available', true)
    .order('is_featured', { ascending: false })
    .order('created_at', { ascending: false })
    .limit(limit)

  if (error) { console.error('[db.getFeaturedCars]', error); return [] }
  return (data as unknown as DbCarRow[]).map(toAppCar)
}

export async function getRelatedCars(carId: string, type: string, limit = 3): Promise<Car[]> {
  const { data: typeRow } = await supabaseAdmin
    .from('car_types')
    .select('id')
    .eq('name', type)
    .single()

  if (!typeRow) return []

  const { data, error } = await supabaseAdmin
    .from('cars')
    .select(CAR_SELECT)
    .eq('is_available', true)
    .eq('car_type_id', typeRow.id)
    .neq('id', carId)
    .order('created_at', { ascending: false })
    .limit(limit)

  if (error) return []
  return (data as unknown as DbCarRow[]).map(toAppCar)
}

// Returns cars by IDs (used by AI recommendation after vector search)
export async function getCarsByIds(ids: string[]): Promise<Car[]> {
  if (!ids.length) return []
  const { data, error } = await supabaseAdmin
    .from('cars')
    .select(CAR_SELECT)
    .in('id', ids)
    .eq('is_available', true)

  if (error) return []
  // Preserve order from the ids array (similarity rank)
  const map = new Map((data as unknown as DbCarRow[]).map((r) => [r.id, toAppCar(r)]))
  return ids.map((id) => map.get(id)).filter(Boolean) as Car[]
}

// Builds the text content used to generate an embedding for a car
export function buildCarEmbeddingContent(car: Car & { fuel?: string; transmission?: string }): string {
  return [
    `${car.make} ${car.model} ${car.year}`,
    `Type: ${car.type}`,
    `Fuel: ${car.fuel ?? 'Gasoline'}`,
    `Transmission: ${car.transmission ?? 'Automatic'}`,
    `Price: $${car.price.toLocaleString()} (estimated value $${car.estimatedValue?.toLocaleString()})`,
    `Mileage: ${car.mileage.toLocaleString()}km`,
    `Seats: ${car.seats ?? 5}`,
    `Location: ${car.location}`,
    car.description,
    car.pros.length ? `Pros: ${car.pros.join(', ')}` : '',
    car.cons.length ? `Cons: ${car.cons.join(', ')}` : '',
  ].filter(Boolean).join('. ')
}
