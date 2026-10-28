import { createServerClient } from '@supabase/auth-helpers-nextjs'
import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { getCarsPage, type CarFilters } from '@/lib/db'
import { supabaseAdmin } from '@/lib/supabase-server'
import { estimatePrice, getPriceLabel } from '@/lib/priceEstimation'

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl

  const filters: CarFilters = {
    priceMin:  searchParams.get('priceMin')  ? Number(searchParams.get('priceMin'))  : undefined,
    priceMax:  searchParams.get('priceMax')  ? Number(searchParams.get('priceMax'))  : undefined,
    type:      searchParams.get('type')      ?? undefined,
    fuel:      searchParams.get('fuel')      ?? undefined,
    seats:     searchParams.get('seats')     ? Number(searchParams.get('seats'))     : undefined,
    location:  searchParams.get('location')  ?? undefined,
    q:         searchParams.get('q')         ?? undefined,
    sortBy:    (searchParams.get('sort') as CarFilters['sortBy']) ?? 'newest',
    limit:     searchParams.get('limit')     ? Number(searchParams.get('limit'))     : 50,
    offset:    searchParams.get('offset')    ? Number(searchParams.get('offset'))    : undefined,
  }

  const { cars, total } = await getCarsPage(filters)
  return NextResponse.json({ cars, count: cars.length, total })
}

export async function POST(request: NextRequest) {
  const cookieStore = await cookies()

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch { /* read-only in route handlers — safe to ignore */ }
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // Only seller accounts can list cars
  const { data: profile } = await supabaseAdmin.from('profiles').select('role').eq('id', user.id).single()
  if (profile?.role !== 'seller') {
    return NextResponse.json({ error: 'Only seller accounts can list cars. Switch to a seller account first.' }, { status: 403 })
  }

  const body = await request.json()
  const { make, model, year, price, mileage, type, fuel, transmission,
          location, description, sellerName, sellerPhone,
          color, seats, pros, cons, imageUrl } = body

  if (!make || !model || !year || !price || !mileage || !type || !fuel ||
      !transmission || !location || !description || !sellerName || !sellerPhone) {
    return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
  }

  // Look up (or create) lookup IDs
  async function lookupOrCreate(table: string, name: string, extra?: Record<string, string>) {
    const { data } = await supabaseAdmin.from(table).select('id').eq('name', name).single()
    if (data) return data.id as string
    const { data: created } = await supabaseAdmin
      .from(table).insert({ name, ...extra }).select('id').single()
    return created?.id as string
  }

  const [brandId, carTypeId, fuelTypeId, transmissionId] = await Promise.all([
    lookupOrCreate('brands', make, { country: 'Unknown' }),
    lookupOrCreate('car_types', type),
    lookupOrCreate('fuel_types', fuel),
    lookupOrCreate('transmissions', transmission),
  ])

  if (!brandId || !carTypeId || !fuelTypeId || !transmissionId) {
    return NextResponse.json({ error: 'Failed to resolve lookup values' }, { status: 500 })
  }

  const estimatedValue = estimatePrice(make, model, Number(year), Number(mileage))
  const priceLabel = getPriceLabel(Number(price), estimatedValue)

  const { data: car, error } = await supabaseAdmin
    .from('cars')
    .insert({
      title: `${year} ${make} ${model}`,
      brand_id: brandId,
      model,
      year: Number(year),
      car_type_id: carTypeId,
      fuel_type_id: fuelTypeId,
      transmission_id: transmissionId,
      price_usd: Number(price),
      estimated_value_usd: estimatedValue,
      price_label: priceLabel,
      mileage_km: Number(mileage),
      color: color || null,
      seats: Number(seats) || 5,
      location,
      description,
      source: 'user',
      seller_name: sellerName,
      seller_phone: sellerPhone,
      seller_id: user.id,
    })
    .select('id')
    .single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  if (imageUrl) {
    await supabaseAdmin.from('car_images').insert({
      car_id: car.id, url: imageUrl, is_primary: true, display_order: 0,
    })
  }

  const features = [
    ...((pros as string[]) ?? []).filter(Boolean).map((f) => ({ car_id: car.id, feature: f, is_pro: true })),
    ...((cons as string[]) ?? []).filter(Boolean).map((f) => ({ car_id: car.id, feature: f, is_pro: false })),
  ]
  if (features.length) await supabaseAdmin.from('car_features').insert(features)

  return NextResponse.json({ id: car.id }, { status: 201 })
}
