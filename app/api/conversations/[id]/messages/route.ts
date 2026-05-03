import { createServerClient } from '@supabase/auth-helpers-nextjs'
import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { supabaseAdmin } from '@/lib/supabase-server'

async function getUser() {
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

async function assertParticipant(conversationId: string, userId: string) {
  const { data } = await supabaseAdmin
    .from('conversations')
    .select('id, buyer_id, seller_id')
    .eq('id', conversationId)
    .single()
  if (!data) return null
  if (data.buyer_id !== userId && data.seller_id !== userId) return null
  return data
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const user = await getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const conv = await assertParticipant(id, user.id)
  if (!conv) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const { data: messages, error } = await supabaseAdmin
    .from('messages')
    .select('id, sender_id, message_type, content, file_url, file_name, file_size, duration_secs, is_read, created_at, profiles ( full_name )')
    .eq('conversation_id', id)
    .order('created_at', { ascending: true })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  // Mark incoming messages as read
  await supabaseAdmin
    .from('messages')
    .update({ is_read: true })
    .eq('conversation_id', id)
    .eq('is_read', false)
    .neq('sender_id', user.id)

  return NextResponse.json({ messages })
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const user = await getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const conv = await assertParticipant(id, user.id)
  if (!conv) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const body = await request.json()
  const {
    message_type = 'text',
    content,
    file_url,
    file_name,
    file_size,
    duration_secs,
  } = body

  if (message_type === 'text' && !content?.trim()) {
    return NextResponse.json({ error: 'Empty message' }, { status: 400 })
  }
  if (message_type !== 'text' && !file_url) {
    return NextResponse.json({ error: 'Missing file_url' }, { status: 400 })
  }

  const { data: message, error } = await supabaseAdmin
    .from('messages')
    .insert({
      conversation_id: id,
      sender_id: user.id,
      message_type,
      content: message_type === 'text' ? content.trim() : null,
      file_url: file_url ?? null,
      file_name: file_name ?? null,
      file_size: file_size ?? null,
      duration_secs: duration_secs ?? null,
    })
    .select('id, sender_id, message_type, content, file_url, file_name, file_size, duration_secs, is_read, created_at')
    .single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  await supabaseAdmin
    .from('conversations')
    .update({ updated_at: new Date().toISOString() })
    .eq('id', id)

  return NextResponse.json({ message }, { status: 201 })
}
