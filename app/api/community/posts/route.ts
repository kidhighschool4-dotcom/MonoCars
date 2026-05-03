import { NextResponse, type NextRequest } from 'next/server'
import { cookies } from 'next/headers'
import { createServerClient } from '@supabase/auth-helpers-nextjs'
import { supabaseAdmin } from '@/lib/supabase-server'

export async function POST(request: NextRequest) {
  const cookieStore = await cookies()
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { get: (name) => cookieStore.get(name)?.value } }
  )

  const { data: { session } } = await supabase.auth.getSession()
  if (!session) {
    return NextResponse.json({ error: 'Sign in to post' }, { status: 401 })
  }

  const { content, post_type, image_urls } = await request.json()

  if (!content?.trim()) {
    return NextResponse.json({ error: 'Content is required' }, { status: 400 })
  }

  const { data: post, error } = await supabaseAdmin
    .from('community_posts')
    .insert({ user_id: session.user.id, content: content.trim(), post_type: post_type ?? 'discussion' })
    .select('id')
    .single()

  if (error || !post) {
    return NextResponse.json({ error: 'Failed to create post' }, { status: 500 })
  }

  if (image_urls?.length) {
    await supabaseAdmin.from('post_images').insert(
      image_urls.map((url: string, i: number) => ({ post_id: post.id, url, display_order: i }))
    )
  }

  return NextResponse.json({ post }, { status: 201 })
}
