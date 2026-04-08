'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Menu, X, Car, Calendar, Users, PlusCircle, LogOut, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '@/lib/auth-context'

const navLinks = [
  { href: '/cars',      label: 'Cars',          icon: Car },
  { href: '/recommend', label: 'AI Advisor',     icon: Sparkles },
  { href: '/events',    label: 'Events',         icon: Calendar },
  { href: '/community', label: 'Community',      icon: Users },
  { href: '/submit',    label: 'Submit Listing', icon: PlusCircle },
]

export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { user, signOut, loading } = useAuth()

  const handleSignOut = async () => {
    await signOut()
    router.push('/')
    setMobileOpen(false)
  }

  const initials = user?.user_metadata?.full_name
    ? user.user_metadata.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0].toUpperCase() ?? '?'

  return (
    <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-gray-100 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-full bg-[#CBA135] flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow">
              <span className="text-[#1A1A1A] font-black text-base leading-none">M</span>
            </div>
            <span className="font-bold text-xl text-[#1A1A1A] tracking-tight">
              Mono<span className="text-[#CBA135]">Cars</span>
            </span>
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={clsx(
                  'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                  link.href === '/submit'
                    ? 'bg-[#CBA135] text-[#1A1A1A] hover:bg-[#b8922e] ml-2'
                    : pathname === link.href
                    ? 'text-[#CBA135] bg-amber-50'
                    : 'text-gray-600 hover:text-[#1A1A1A] hover:bg-gray-50'
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          {/* Auth + Mobile Toggle */}
          <div className="flex items-center gap-3">
            {!loading && (
              user ? (
                <div className="hidden md:flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-[#CBA135] flex items-center justify-center">
                    <span className="text-[#1A1A1A] font-bold text-xs">{initials}</span>
                  </div>
                  <button
                    onClick={handleSignOut}
                    className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all duration-200"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </div>
              ) : (
                <Link
                  href="/auth"
                  className="hidden md:inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-600 hover:text-[#1A1A1A] hover:bg-gray-50 rounded-lg transition-all duration-200"
                >
                  Sign In
                </Link>
              )
            )}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors"
              aria-label="Toggle menu"
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-gray-100 bg-white/95 backdrop-blur-md">
          <div className="px-4 py-3 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={clsx(
                  'flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all',
                  link.href === '/submit'
                    ? 'bg-[#CBA135] text-[#1A1A1A]'
                    : pathname === link.href
                    ? 'text-[#CBA135] bg-amber-50'
                    : 'text-gray-700 hover:bg-gray-50'
                )}
              >
                <link.icon className="w-4 h-4" />
                {link.label}
              </Link>
            ))}
            {user ? (
              <button
                onClick={handleSignOut}
                className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium text-red-600 hover:bg-red-50 transition-all w-full text-left"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            ) : (
              <Link
                href="/auth"
                onClick={() => setMobileOpen(false)}
                className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition-all"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      )}
    </header>
  )
}
