import Link from 'next/link'
import { redirect } from 'next/navigation'
import { Plus } from 'lucide-react'
import { getServerUser, getAccountRole } from '@/lib/auth-server'
import { supabaseAdmin } from '@/lib/supabase-server'
import PageHeader from '@/components/ui/PageHeader'
import SafeImage from '@/components/ui/SafeImage'
import Badge from '@/components/ui/Badge'

export const dynamic = 'force-dynamic'

interface SellerCarRow {
  id: string
  title: string
  price_usd: number
  price_label: string
  is_available: boolean
  created_at: string
  location: string
  car_images: { url: string; display_order: number }[]
}

export default async function SellerDashboard() {
  const user = await getServerUser()
  if (!user) redirect('/auth?type=seller&next=/seller')
  if ((await getAccountRole(user.id)) !== 'seller') redirect('/account')

  const { data } = await supabaseAdmin
    .from('cars')
    .select('id, title, price_usd, price_label, is_available, created_at, location, car_images(url, display_order)')
    .eq('seller_id', user.id)
    .order('created_at', { ascending: false })
  const cars = (data ?? []) as SellerCarRow[]

  return (
    <div className="min-h-screen">
      <PageHeader eyebrow="Seller" title="My listings" description="Everything you have listed on FBM.">
        <Link href="/submit" className="mt-6 inline-flex items-center gap-2 px-5 py-3 rounded-full bg-brand text-white text-sm font-semibold hover:bg-brand-strong transition-colors">
          <Plus className="w-4 h-4" /> List a car
        </Link>
      </PageHeader>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {cars.length === 0 ? (
          <div className="text-center py-20 rounded-3xl border border-dashed border-line bg-surface">
            <p className="text-lg font-semibold text-ink">No listings yet</p>
            <p className="text-muted mt-1">List your first car — it&apos;s free and gets an instant AI price check.</p>
          </div>
        ) : (
          <ul className="divide-y divide-line rounded-3xl border border-line bg-surface overflow-hidden">
            {cars.map((c) => {
              const img = [...(c.car_images ?? [])].sort((a, b) => a.display_order - b.display_order)[0]?.url ?? ''
              return (
                <li key={c.id}>
                  <Link href={`/cars/${c.id}`} className="flex items-center gap-4 p-4 hover:bg-paper transition-colors">
                    <SafeImage src={img} alt="" className="w-24 h-18 aspect-[4/3] rounded-xl object-cover flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-ink truncate">{c.title}</p>
                      <p className="text-sm text-muted">{c.location} · listed {new Date(c.created_at).toLocaleDateString('en-GB')}</p>
                    </div>
                    <div className="hidden sm:block"><Badge label={c.price_label} size="sm" /></div>
                    <div className="text-right">
                      <p className="font-semibold text-ink tnum">${c.price_usd.toLocaleString()}</p>
                      <p className={c.is_available ? 'text-xs text-emerald-700' : 'text-xs text-muted'}>
                        {c.is_available ? 'Live' : 'Hidden'}
                      </p>
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
