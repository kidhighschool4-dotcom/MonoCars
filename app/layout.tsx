import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Header from '@/components/layout/Header'
import Footer from '@/components/layout/Footer'
import { AuthProvider } from '@/lib/auth-context'

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: "MonoCars | Cambodia's Car Platform",
  description:
    "Cambodia's premier car intelligence platform. Find smart pricing insights, trusted listings, and a community that knows cars.",
  keywords: ['cars', 'Cambodia', 'Phnom Penh', 'car listings', 'used cars', 'motor vehicles'],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-[#F8F5F0] text-[#1A1A1A] min-h-screen flex flex-col">
        <AuthProvider>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  )
}
