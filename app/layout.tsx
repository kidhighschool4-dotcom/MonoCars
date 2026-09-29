import type { Metadata } from 'next'
import { Parkinsans, Kantumruy_Pro } from 'next/font/google'
import './globals.css'
import Header from '@/components/layout/Header'
import Footer from '@/components/layout/Footer'
import { AuthProvider } from '@/lib/auth-context'

const parkinsans = Parkinsans({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-parkinsans',
})

const kantumruy = Kantumruy_Pro({
  subsets: ['khmer', 'latin'],
  display: 'swap',
  variable: '--font-kantumruy',
})

export const metadata: Metadata = {
  title: "FBM | Cambodia's Car Marketplace",
  description:
    'Find, compare and buy cars in Cambodia with honest AI price checks, trusted sellers and a community that knows cars.',
  keywords: ['FBM', 'cars', 'Cambodia', 'Phnom Penh', 'car listings', 'used cars', 'car prices'],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${parkinsans.variable} ${kantumruy.variable}`}>
      <body className="bg-paper text-ink min-h-screen flex flex-col">
        <AuthProvider>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  )
}
