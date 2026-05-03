import { createServerClient } from '@supabase/auth-helpers-nextjs'
import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { supabaseAdmin } from '@/lib/supabase-server'

export async function POST(request: NextRequest) {
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
  const user = (await supabase.auth.getUser()).data.user
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { conversationId, fileName } = await request.json()
  if (!conversationId || !fileName) {
    return NextResponse.json({ error: 'Missing conversationId or fileName' }, { status: 400 })
  }

  // Verify participant
  const { data: conv } = await supabaseAdmin
    .from('conversations')
    .select('id')
    .eq('id', conversationId)
    .or(`buyer_id.eq.${user.id},seller_id.eq.${user.id}`)
    .single()

  if (!conv) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const ext = fileName.includes('.') ? fileName.split('.').pop() : ''
  const filePath = `${user.id}/${conversationId}/${Date.now()}${ext ? '.' + ext : ''}`

  const { data, error } = await supabaseAdmin.storage
    .from('chat-media')
    .createSignedUploadUrl(filePath)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  const { data: { publicUrl } } = supabaseAdmin.storage.from('chat-media').getPublicUrl(filePath)

  return NextResponse.json({ signedUrl: data.signedUrl, fileUrl: publicUrl })
}
