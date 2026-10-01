'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  Menu, X, Car, Calendar, Users, LogOut, Sparkles, MessageCircle, ArrowUpRight, UserRound, Store,
  Target, Database, Gauge, LogIn,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '@/lib/auth-context'
import Logo from '@/components/brand/Logo'

type NavItem = { href: string; label: string; icon: typeof Car; hint?: string }

const navLinks: NavItem[] = [
  { href: '/cars',      label: 'Buy a car',  icon: Car },
  { href: '/recommend', label: 'AI Advisor', icon: Sparkles },
  { href: '/events',    label: 'Events',     icon: Calendar },
  { href: '/community', label: 'Community',  icon: Users },
]

export default function Header() {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { user, profile, signOut, loading } = useAuth()
  const panelRef = useRef<HTMLDivElement>(null)
  const isSeller = profile?.role === 'seller'
  const isAdminUser = user?.app_metadata?.role === 'admin'
  // Convenience only — the pages themselves are protected server-side (lib/auth-server.ts canViewFacebookData)
  const canSeeData = user?.email?.toLowerCase() === 'kimhengpanha0105@gmail.com'

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`)

  // close on Escape and outside click (links close it themselves)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onClick) }
  }, [open])

  const handleSignOut = async () => {
    await signOut()
    setOpen(false)
    router.push('/')
  }

  const initials = user?.user_metadata?.full_name
    ? user.user_metadata.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0].toUpperCase() ?? '?'

  const accountLinks: NavItem[] = user ? [
    { href: '/messages', label: 'Messages', icon: MessageCircle },
    { href: '/account', label: 'Account', icon: UserRound },
    ...(isSeller ? [{ href: '/seller', label: 'My listings', icon: Store }] : []),
  ] : []
  const dataLinks: NavItem[] = [
    ...(canSeeData ? [
      { href: '/admin/social', label: 'RX300 buyers', icon: Target, hint: 'Leads from every platform' },
      { href: '/admin/facebook', label: 'Facebook data', icon: Database, hint: 'Posts, comments, screenshots' },
    ] : []),
    ...(isAdminUser ? [{ href: '/admin/intelligence', label: 'Listing intelligence', icon: Gauge, hint: 'Crawled listings & reviews' }] : []),
  ]

  const Item = ({ l }: { l: NavItem }) => (
    <Link
      href={l.href}
      onClick={() => setOpen(false)}
      className={clsx('group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors',
        isActive(l.href) ? 'bg-brand-soft text-brand' : 'text-ink hover:bg-paper')}
    >
      <l.icon className={clsx('w-[18px] h-[18px] flex-shrink-0', isActive(l.href) ? 'text-brand' : 'text-muted group-hover:text-ink')} />
      <span className="min-w-0">
        <span className="block text-[15px] font-medium leading-tight">{l.label}</span>
        {l.hint && <span className="block text-xs text-muted leading-tight mt-0.5">{l.hint}</span>}
      </span>
    </Link>
  )

  return (
    <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-xl border-b border-line">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          <Link href="/" aria-label="FBM home" className="flex-shrink-0">
            <Logo />
          </Link>

          <nav className="hidden lg:flex items-center gap-1" aria-label="Main">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive(link.href) ? 'page' : undefined}
                className={clsx('px-3.5 py-2 rounded-full text-[15px] font-medium whitespace-nowrap transition-colors',
                  isActive(link.href) ? 'text-ink bg-paper' : 'text-muted hover:text-ink')}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-2 flex-shrink-0" ref={panelRef}>
            <Link
              href="/submit"
              className="hidden sm:inline-flex items-center gap-1.5 pl-4 pr-3 py-2 rounded-full bg-ink text-white text-sm font-semibold whitespace-nowrap hover:bg-brand transition-colors"
            >
              Sell your car <ArrowUpRight className="w-4 h-4" />
            </Link>

            {!loading && user && (
              <Link href="/account" aria-label="Your account" title={user.email ?? ''}
                className="hidden sm:flex w-9 h-9 rounded-full bg-paper border border-line items-center justify-center text-ink text-xs font-semibold hover:border-ink transition-colors">
                {initials}
              </Link>
            )}

            <div className="relative">
              <button
                onClick={() => setOpen((v) => !v)}
                className={clsx('flex items-center gap-2 h-9 pl-2.5 pr-3 rounded-full border transition-colors',
                  open ? 'border-ink bg-ink text-white' : 'border-line text-ink hover:border-ink')}
                aria-label={open ? 'Close menu' : 'Open menu'}
                aria-expanded={open}
                aria-haspopup="menu"
              >
                {open ? <X className="w-[18px] h-[18px]" /> : <Menu className="w-[18px] h-[18px]" />}
                <span className="text-sm font-medium hidden sm:inline">Menu</span>
                {canSeeData && !open && <span className="w-1.5 h-1.5 rounded-full bg-brand" aria-hidden="true" />}
              </button>

              {open && (
                <div
                  role="menu"
                  className="absolute right-0 top-[calc(100%+10px)] w-[min(340px,calc(100vw-2rem))] max-h-[calc(100dvh-5rem)] overflow-y-auto
                             bg-white rounded-2xl border border-line shadow-[0_18px_50px_-12px_rgba(0,0,0,0.25)]"
                >
                  <div className="p-3">
                    <div className="lg:hidden">
                      <p className="px-3 pt-1 pb-2 text-[11px] font-semibold uppercase tracking-wider text-subtle">Browse</p>
                      {navLinks.map((l) => <Item key={l.href} l={l} />)}
                      <div className="my-2 border-t border-line" />
                    </div>

                    {dataLinks.length > 0 && (
                      <>
                        <p className="px-3 pt-1 pb-2 text-[11px] font-semibold uppercase tracking-wider text-subtle">Your data</p>
                        {dataLinks.map((l) => <Item key={l.href} l={l} />)}
                        <div className="my-2 border-t border-line" />
                      </>
                    )}

                    {accountLinks.length > 0 && (
                      <>
                        <p className="px-3 pt-1 pb-2 text-[11px] font-semibold uppercase tracking-wider text-subtle">Account</p>
                        {accountLinks.map((l) => <Item key={l.href} l={l} />)}
                        <div className="my-2 border-t border-line" />
                      </>
                    )}

                    <div className="sm:hidden px-1 pb-2">
                      <Link href="/submit" onClick={() => setOpen(false)} className="flex items-center justify-center gap-2 py-3 rounded-xl bg-ink text-white font-semibold">
                        Sell your car <ArrowUpRight className="w-4 h-4" />
                      </Link>
                    </div>

                    {user ? (
                      <button onClick={handleSignOut} className="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-ink hover:bg-paper transition-colors">
                        <LogOut className="w-[18px] h-[18px] text-muted" />
                        <span className="text-[15px] font-medium">Sign out</span>
                        <span className="ml-auto text-xs text-subtle truncate max-w-[150px]">{user.email}</span>
                      </button>
                    ) : (
                      <Link href="/auth" onClick={() => setOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-ink hover:bg-paper transition-colors">
                        <LogIn className="w-[18px] h-[18px] text-muted" />
                        <span className="text-[15px] font-medium">Sign in</span>
                      </Link>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
