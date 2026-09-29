import Link from 'next/link'
import { ArrowUpRight, Mail, Phone, MapPin } from 'lucide-react'
import Logo from '@/components/brand/Logo'

// Placeholder contact details — replace with FBM's real ones before launch.
const CONTACT = {
  email: 'hello@fbm.kh',
  phone: '+855 23 123 456',
  address: 'Phnom Penh, Cambodia',
  social: {
    facebook: '#',
    telegram: '#',
    instagram: '#',
  },
}

const columns = [
  {
    title: 'Explore',
    links: [
      { href: '/cars', label: 'Buy a car' },
      { href: '/submit', label: 'Sell your car' },
      { href: '/recommend', label: 'AI Advisor' },
      { href: '/events', label: 'Events' },
      { href: '/community', label: 'Community' },
    ],
  },
  {
    title: 'Company',
    links: [
      { href: '#', label: 'About' },
      { href: '#', label: 'Contact' },
      { href: '#', label: 'Privacy' },
      { href: '#', label: 'Terms' },
    ],
  },
]

const socials = [
  {
    label: 'Facebook',
    href: CONTACT.social.facebook,
    path: 'M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z',
  },
  {
    label: 'Telegram',
    href: CONTACT.social.telegram,
    path: 'M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.96 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z',
  },
  {
    label: 'Instagram',
    href: CONTACT.social.instagram,
    path: 'M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z',
  },
]

export default function Footer() {
  return (
    <footer className="bg-ink text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Closing CTA */}
        <div className="py-16 md:py-20 border-b border-ink-3 flex flex-col md:flex-row md:items-end md:justify-between gap-8">
          <div>
            <p className="text-subtle text-sm mb-3">Ready when you are</p>
            <h2 className="text-4xl md:text-6xl font-semibold tracking-tight leading-[1.05] max-w-2xl">
              Your next car is <span className="text-brand">already here.</span>
            </h2>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/cars"
              className="inline-flex items-center gap-2 px-6 py-3.5 rounded-full bg-brand text-white font-semibold hover:bg-brand-strong transition-colors"
            >
              Browse cars <ArrowUpRight className="w-4 h-4" />
            </Link>
            <Link
              href="/submit"
              className="inline-flex items-center gap-2 px-6 py-3.5 rounded-full border border-ink-3 text-white font-semibold hover:border-white transition-colors"
            >
              Sell your car
            </Link>
          </div>
        </div>

        {/* Links */}
        <div className="py-14 grid grid-cols-2 md:grid-cols-12 gap-10">
          <div className="col-span-2 md:col-span-5">
            <Logo tone="light" size="lg" />
            <p className="text-subtle text-[15px] leading-relaxed mt-5 max-w-sm">
              Cambodia&apos;s car marketplace. Honest AI price checks, trusted sellers, and a community that knows cars.
            </p>
            <p className="text-subtle/80 text-sm mt-2" lang="km">ទិញ លក់ និងប្រៀបធៀបរថយន្តនៅកម្ពុជា</p>
            <div className="mt-6 flex items-center gap-2">
              {socials.map((s) => (
                <a
                  key={s.label}
                  href={s.href}
                  aria-label={s.label}
                  className="w-10 h-10 rounded-full border border-ink-3 flex items-center justify-center text-white hover:bg-brand hover:border-brand transition-colors"
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d={s.path} /></svg>
                </a>
              ))}
            </div>
          </div>

          {columns.map((col) => (
            <div key={col.title} className="md:col-span-2">
              <h3 className="text-subtle text-sm mb-4">{col.title}</h3>
              <ul className="space-y-3">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <Link href={link.href} className="text-[15px] text-white/90 hover:text-brand transition-colors">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <div className="col-span-2 md:col-span-3">
            <h3 className="text-subtle text-sm mb-4">Contact</h3>
            <ul className="space-y-3 text-[15px] text-white/90">
              <li className="flex items-center gap-2.5">
                <Mail className="w-4 h-4 text-brand flex-shrink-0" />
                <a href={`mailto:${CONTACT.email}`} className="hover:text-brand transition-colors">{CONTACT.email}</a>
              </li>
              <li className="flex items-center gap-2.5">
                <Phone className="w-4 h-4 text-brand flex-shrink-0" />
                <a href={`tel:${CONTACT.phone.replace(/\s/g, '')}`} className="hover:text-brand transition-colors tnum">{CONTACT.phone}</a>
              </li>
              <li className="flex items-center gap-2.5">
                <MapPin className="w-4 h-4 text-brand flex-shrink-0" />
                <span>{CONTACT.address}</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Big wordmark */}
        <div className="select-none pointer-events-none overflow-hidden" aria-hidden="true">
          <p className="font-bold tracking-tighter leading-[0.8] text-[28vw] md:text-[22vw] lg:text-[300px] text-white/[0.04] -mb-[0.12em]">
            FBM.
          </p>
        </div>

        <div className="py-6 border-t border-ink-3 flex flex-col sm:flex-row justify-between gap-2 text-sm text-subtle">
          <p>&copy; {new Date().getFullYear()} FBM. All rights reserved.</p>
          <p>Made in Cambodia 🇰🇭</p>
        </div>
      </div>
    </footer>
  )
}
