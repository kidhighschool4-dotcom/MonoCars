'use client'

import Link from 'next/link'
import { ShoppingBag, Store, ArrowUpRight } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import PageHeader from '@/components/ui/PageHeader'
import SwitchRoleButton from '@/components/account/SwitchRoleButton'

export default function AccountPage() {
  const { user, profile, loading } = useAuth()

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-24 text-muted">Loading…</div>

  if (!user) {
    return (
      <div className="max-w-md mx-auto px-4 py-24 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Your account</h1>
        <p className="text-muted mt-3 mb-6">Sign in to manage your account.</p>
        <Link href="/auth" className="inline-flex px-6 py-3 rounded-full bg-ink text-white font-semibold hover:bg-brand transition-colors">
          Sign in
        </Link>
      </div>
    )
  }

  const isSeller = profile?.role === 'seller'

  return (
    <div className="min-h-screen">
      <PageHeader eyebrow="Account" title={profile?.full_name || 'Your account'} description={user.email ?? undefined} />
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
        <section className="bg-surface rounded-3xl border border-line p-6 md:p-8">
          <p className="text-sm text-muted">Account type</p>
          <div className="mt-3 flex items-center gap-4">
            <span className="w-12 h-12 rounded-2xl bg-brand-soft text-brand flex items-center justify-center">
              {isSeller ? <Store className="w-6 h-6" /> : <ShoppingBag className="w-6 h-6" />}
            </span>
            <div>
              <p className="text-xl font-semibold text-ink">{isSeller ? 'Seller' : 'Customer'}</p>
              <p className="text-sm text-muted">
                {isSeller ? 'You can list cars and reply to buyers.' : 'You can browse cars, use the AI Advisor and message sellers.'}
              </p>
            </div>
          </div>
          <div className="mt-6 pt-6 border-t border-line flex flex-wrap items-center gap-3">
            {isSeller ? (
              <>
                <Link href="/seller" className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors">
                  My listings <ArrowUpRight className="w-4 h-4" />
                </Link>
                <SwitchRoleButton to="customer" label="Switch to customer account" variant="outline" />
              </>
            ) : (
              <SwitchRoleButton to="seller" label="Become a seller" variant="outline" />
            )}
          </div>
        </section>

        <section className="bg-surface rounded-3xl border border-line p-6 md:p-8 grid sm:grid-cols-2 gap-3">
          <Link href="/messages" className="rounded-2xl border border-line p-4 hover:border-ink transition-colors">
            <p className="font-semibold text-ink">Messages</p>
            <p className="text-sm text-muted">Chats with {isSeller ? 'buyers' : 'sellers'}</p>
          </Link>
          <Link href={isSeller ? '/submit' : '/cars'} className="rounded-2xl border border-line p-4 hover:border-ink transition-colors">
            <p className="font-semibold text-ink">{isSeller ? 'List a car' : 'Browse cars'}</p>
            <p className="text-sm text-muted">{isSeller ? 'Free, with an instant AI price check' : 'Every listing has an AI price check'}</p>
          </Link>
        </section>
      </div>
    </div>
  )
}
