import { createServerClient } from '@supabase/auth-helpers-nextjs'
import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { supabaseAdmin } from '@/lib/supabase-server'

async function getUser(request: NextRequest) {
  const cookieStore = await cookies()
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet) {
          try { cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options)) } catch {}
        },
      },
    }
  )
  return (await supabase.auth.getUser()).data.user
}

// GET: list all conversations for current user
export async function GET(request: NextRequest) {
  const user = await getUser(request)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { data, error } = await supabaseAdmin
    .from('conversations')
    .select(`
      id, car_id, buyer_id, seller_id, created_at, updated_at,
      cars ( id, title, price_usd, car_images ( url, is_primary ) ),
      buyer:profiles!conversations_buyer_id_fkey ( id, full_name ),
      seller:profiles!conversations_seller_id_fkey ( id, full_name )
    `)
    .or(`buyer_id.eq.${user.id},seller_id.eq.${user.id}`)
    .order('updated_at', { ascending: false })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ conversations: data })
}

// POST: create or get existing conversation
export async function POST(request: NextRequest) {
  const user = await getUser(request)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { carId, sellerId } = await request.json()
  if (!carId || !sellerId) return NextResponse.json({ error: 'Missing fields' }, { status: 400 })
  if (user.id === sellerId) return NextResponse.json({ error: 'Cannot message yourself' }, { status: 400 })

  // Return existing if any
  const { data: existing } = await supabaseAdmin
    .from('conversations')
    .select('id')
    .eq('car_id', carId)
    .eq('buyer_id', user.id)
    .single()

  if (existing) return NextResponse.json({ id: existing.id })

  const { data: conv, error } = await supabaseAdmin
    .from('conversations')
    .insert({ car_id: carId, buyer_id: user.id, seller_id: sellerId })
    .select('id')
    .single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ id: conv.id }, { status: 201 })
}
