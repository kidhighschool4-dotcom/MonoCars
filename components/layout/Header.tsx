'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Menu, X, Car, Calendar, Users, PlusCircle, LogOut, Sparkles, MessageCircle, ArrowUpRight, UserRound, Store } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '@/lib/auth-context'
import Logo from '@/components/brand/Logo'

const navLinks = [
  { href: '/cars',      label: 'Buy a car',  icon: Car },
  { href: '/recommend', label: 'AI Advisor', icon: Sparkles },
  { href: '/events',    label: 'Events',     icon: Calendar },
  { href: '/community', label: 'Community',  icon: Users },
]

export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { user, profile, signOut, loading } = useAuth()
  const isSeller = profile?.role === 'seller'
  const isAdminUser = user?.app_metadata?.role === 'admin'
  // Convenience only — the page itself is protected server-side (lib/auth-server.ts canViewFacebookData)
  const canSeeFacebook = user?.email?.toLowerCase() === 'kimhengpanha0105@gmail.com'

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`)

  const handleSignOut = async () => {
    await signOut()
    router.push('/')
    setMobileOpen(false)
  }

  const initials = user?.user_metadata?.full_name
    ? user.user_metadata.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0].toUpperCase() ?? '?'

  return (
    <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-line">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" aria-label="FBM home" onClick={() => setMobileOpen(false)}>
            <Logo />
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1" aria-label="Main">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive(link.href) ? 'page' : undefined}
                className={clsx(
                  'px-3.5 py-2 rounded-full text-[15px] font-medium transition-colors',
                  isActive(link.href)
                    ? 'text-ink bg-paper'
                    : 'text-muted hover:text-ink'
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {!loading && (
              user ? (
                <div className="hidden md:flex items-center gap-1">
                  <Link
                    href="/messages"
                    aria-label="Messages"
                    className={clsx(
                      'p-2.5 rounded-full transition-colors',
                      isActive('/messages') ? 'text-brand bg-brand-soft' : 'text-muted hover:text-ink hover:bg-paper'
                    )}
                  >
                    <MessageCircle className="w-5 h-5" />
                  </Link>
                  <button
                    onClick={handleSignOut}
                    aria-label="Sign out"
                    className="p-2.5 rounded-full text-muted hover:text-ink hover:bg-paper transition-colors"
                  >
                    <LogOut className="w-5 h-5" />
                  </button>
                  {canSeeFacebook && (
                    <Link href="/admin/facebook" className={clsx('px-3 py-2 rounded-full text-sm font-medium transition-colors', isActive('/admin/facebook') ? 'text-brand bg-brand-soft' : 'text-muted hover:text-ink')}>
                      Facebook data
                    </Link>
                  )}
                  {isAdminUser && (
                    <Link href="/admin/intelligence" className={clsx('px-3 py-2 rounded-full text-sm font-medium transition-colors', isActive('/admin') ? 'text-brand bg-brand-soft' : 'text-muted hover:text-ink')}>
                      Intelligence
                    </Link>
                  )}
                  {isSeller && (
                    <Link href="/seller" className={clsx('px-3 py-2 rounded-full text-sm font-medium transition-colors', isActive('/seller') ? 'text-brand bg-brand-soft' : 'text-muted hover:text-ink')}>
                      My listings
                    </Link>
                  )}
                  <Link href="/account" aria-label="Your account" className="w-9 h-9 rounded-full bg-ink flex items-center justify-center ml-1 hover:bg-brand transition-colors" title={user.email ?? ''}>
                    <span className="text-white font-semibold text-xs">{initials}</span>
                  </Link>
                </div>
              ) : (
                <Link
                  href="/auth"
                  className="hidden md:inline-flex px-4 py-2 text-[15px] font-medium text-ink hover:text-brand transition-colors"
                >
                  Sign in
                </Link>
              )
            )}

            <Link
              href="/submit"
              className="hidden sm:inline-flex items-center gap-1.5 pl-4 pr-3 py-2.5 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors"
            >
              Sell your car
              <ArrowUpRight className="w-4 h-4" />
            </Link>

            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2.5 -mr-2 rounded-full text-ink hover:bg-paper transition-colors"
              aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-line bg-white">
          <nav className="px-4 py-4 space-y-1" aria-label="Mobile">
            {[
              ...navLinks,
              ...(user ? [{ href: '/messages', label: 'Messages', icon: MessageCircle }, { href: '/account', label: 'Account', icon: UserRound }] : []),
              ...(isSeller ? [{ href: '/seller', label: 'My listings', icon: Store }] : []),
            ].map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={clsx(
                  'flex items-center gap-3 px-4 py-3.5 rounded-2xl text-base font-medium transition-colors',
                  isActive(link.href) ? 'bg-brand-soft text-brand' : 'text-ink hover:bg-paper'
                )}
              >
                <link.icon className="w-5 h-5" />
                {link.label}
              </Link>
            ))}

            <div className="pt-3 grid grid-cols-2 gap-2">
              <Link
                href="/submit"
                onClick={() => setMobileOpen(false)}
                className="flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-ink text-white font-semibold"
              >
                <PlusCircle className="w-5 h-5" />
                Sell your car
              </Link>
              {user ? (
                <button
                  onClick={handleSignOut}
                  className="flex items-center justify-center gap-2 py-3.5 rounded-2xl border border-line text-ink font-semibold"
                >
                  <LogOut className="w-5 h-5" />
                  Sign out
                </button>
              ) : (
                <Link
                  href="/auth"
                  onClick={() => setMobileOpen(false)}
                  className="flex items-center justify-center py-3.5 rounded-2xl border border-line text-ink font-semibold"
                >
                  Sign in
                </Link>
              )}
            </div>
          </nav>
        </div>
      )}
    </header>
  )
}
