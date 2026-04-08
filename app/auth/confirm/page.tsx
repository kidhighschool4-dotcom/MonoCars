'use client'

import Link from 'next/link'
import { Mail } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function ConfirmContent() {
  const searchParams = useSearchParams()
  const email = searchParams.get('email') ?? 'your email'

  return (
    <div className="min-h-screen bg-[#F8F5F0] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-3xl shadow-sm border border-gray-100 overflow-hidden text-center">
          {/* Header */}
          <div className="bg-[#1A1A1A] px-8 py-8">
            <Link href="/" className="inline-flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-full bg-[#CBA135] flex items-center justify-center">
                <span className="text-[#1A1A1A] font-black text-lg">M</span>
              </div>
              <span className="font-bold text-xl text-white tracking-tight">
                Mono<span className="text-[#CBA135]">Cars</span>
              </span>
            </Link>
          </div>

          <div className="px-8 py-10">
            {/* Icon */}
            <div className="w-16 h-16 rounded-full bg-amber-50 border-2 border-[#CBA135] flex items-center justify-center mx-auto mb-6">
              <Mail className="w-8 h-8 text-[#CBA135]" />
            </div>

            <h1 className="text-2xl font-bold text-[#1A1A1A] mb-3">Check your inbox</h1>
            <p className="text-gray-500 text-sm leading-relaxed mb-2">
              We sent a confirmation link to
            </p>
            <p className="font-semibold text-[#1A1A1A] text-sm mb-6 break-all">{email}</p>
            <p className="text-gray-400 text-sm leading-relaxed mb-8">
              Click the link in the email to activate your account. If you don&apos;t see it, check your spam folder.
            </p>

            <div className="space-y-3">
              <Link
                href="/auth"
                className="block w-full py-3 rounded-xl bg-[#CBA135] text-[#1A1A1A] text-sm font-semibold hover:bg-[#b8922e] transition-colors"
              >
                Back to Sign In
              </Link>
              <Link
                href="/"
                className="block w-full py-3 rounded-xl border border-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Go to MonoCars
              </Link>
            </div>
          </div>
        </div>

        <p className="text-xs text-center text-gray-400 mt-6">
          Wrong email? <Link href="/auth?tab=signup" className="text-[#CBA135] hover:underline">Sign up again</Link> with the correct one.
        </p>
      </div>
    </div>
  )
}

export default function ConfirmPage() {
  return (
    <Suspense>
      <ConfirmContent />
    </Suspense>
  )
}
