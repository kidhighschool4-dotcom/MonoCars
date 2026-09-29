'use client'

import Link from 'next/link'
import Logo from '@/components/brand/Logo'
import { Mail } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function ConfirmContent() {
  const searchParams = useSearchParams()
  const email = searchParams.get('email') ?? 'your email'

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-3xl shadow-sm border border-line overflow-hidden text-center">
          {/* Header */}
          <div className="bg-ink px-8 py-8">
            <Link href="/" className="inline-flex items-center gap-2.5">
              <Logo tone="light" size="lg" />
            </Link>
          </div>

          <div className="px-8 py-10">
            {/* Icon */}
            <div className="w-16 h-16 rounded-full bg-brand-soft border-2 border-brand flex items-center justify-center mx-auto mb-6">
              <Mail className="w-8 h-8 text-brand" />
            </div>

            <h1 className="text-2xl font-bold text-ink mb-3">Check your inbox</h1>
            <p className="text-muted text-sm leading-relaxed mb-2">
              We sent a confirmation link to
            </p>
            <p className="font-semibold text-ink text-sm mb-6 break-all">{email}</p>
            <p className="text-gray-400 text-sm leading-relaxed mb-8">
              Click the link in the email to activate your account. If you don&apos;t see it, check your spam folder.
            </p>

            <div className="space-y-3">
              <Link
                href="/auth"
                className="block w-full py-3 rounded-xl bg-brand text-white text-sm font-semibold hover:bg-brand-strong transition-colors"
              >
                Back to Sign In
              </Link>
              <Link
                href="/"
                className="block w-full py-3 rounded-xl border border-line text-muted text-sm font-medium hover:bg-paper transition-colors"
              >
                Go to FBM
              </Link>
            </div>
          </div>
        </div>

        <p className="text-xs text-center text-gray-400 mt-6">
          Wrong email? <Link href="/auth?tab=signup" className="text-brand hover:underline">Sign up again</Link> with the correct one.
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
