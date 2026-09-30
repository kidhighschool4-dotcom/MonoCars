import { createServerClient } from '@supabase/auth-helpers-nextjs'
import { cookies } from 'next/headers'
import type { User } from '@supabase/supabase-js'
import { supabaseAdmin } from '@/lib/supabase-server'

/** Signed-in user for server components / route handlers (verified with Supabase Auth, not just the cookie). */
export async function getServerUser(): Promise<User | null> {
  const cookieStore = await cookies()
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options))
          } catch { /* read-only in server components */ }
        },
      },
    }
  )
  const { data: { user } } = await supabase.auth.getUser()
  return user
}

export async function getAccountRole(userId: string): Promise<'customer' | 'seller'> {
  const { data } = await supabaseAdmin.from('profiles').select('role').eq('id', userId).single()
  return data?.role === 'seller' ? 'seller' : 'customer'
}

/** Admin = app_metadata.role === 'admin'. app_metadata is only writable with the service role. */
export function isAdmin(user: User | null): boolean {
  return user?.app_metadata?.role === 'admin'
}

/**
 * Facebook data dashboard access: ONLY the accounts listed here (server-side env FB_DASHBOARD_EMAILS,
 * comma-separated; defaults to the owner), and only once their email is confirmed.
 */
export function canViewFacebookData(user: User | null): boolean {
  if (!user?.email || !user.email_confirmed_at) return false
  const allowed = (process.env.FB_DASHBOARD_EMAILS ?? 'kimhengpanha0105@gmail.com')
    .split(',').map((e) => e.trim().toLowerCase()).filter(Boolean)
  return allowed.includes(user.email.toLowerCase())
}
