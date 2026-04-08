import { NextResponse, type NextRequest } from 'next/server'
import { getCars, type CarFilters } from '@/lib/db'

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl

  const filters: CarFilters = {
    priceMin:  searchParams.get('priceMin')  ? Number(searchParams.get('priceMin'))  : undefined,
    priceMax:  searchParams.get('priceMax')  ? Number(searchParams.get('priceMax'))  : undefined,
    type:      searchParams.get('type')      ?? undefined,
    fuel:      searchParams.get('fuel')      ?? undefined,
    seats:     searchParams.get('seats')     ? Number(searchParams.get('seats'))     : undefined,
    location:  searchParams.get('location')  ?? undefined,
    sortBy:    (searchParams.get('sort') as CarFilters['sortBy']) ?? 'newest',
    limit:     searchParams.get('limit')     ? Number(searchParams.get('limit'))     : 50,
    offset:    searchParams.get('offset')    ? Number(searchParams.get('offset'))    : undefined,
  }

  const cars = await getCars(filters)
  return NextResponse.json({ cars, count: cars.length })
}
