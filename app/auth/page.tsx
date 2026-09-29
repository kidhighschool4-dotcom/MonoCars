'use client'

import { useState } from 'react'
import Link from 'next/link'
import Logo from '@/components/brand/Logo'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, ArrowLeft } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'

export default function AuthPage() {
  const router = useRouter()
  const [isSignIn, setIsSignIn] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      if (isSignIn) {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        })
        if (signInError) throw signInError
        setSuccess('Signed in successfully! Redirecting...')
        setTimeout(() => router.push('/'), 800)
      } else {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { full_name: name },
            emailRedirectTo: `${window.location.origin}/auth/callback`,
          },
        })
        if (signUpError) throw signUpError
        router.push(`/auth/confirm?email=${encodeURIComponent(email)}`)
        return
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'An error occurred'
      setError(message.includes('placeholder') ? 'Supabase is not configured yet. Add your credentials to .env.local' : message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink transition-colors mb-8"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to FBM
        </Link>

        <div className="bg-white rounded-3xl shadow-sm border border-line overflow-hidden">
          {/* Header */}
          <div className="bg-ink px-8 py-8 text-center">
            <Link href="/" className="inline-flex items-center gap-2.5 mb-4">
              <Logo tone="light" size="lg" />
            </Link>
            <p className="text-gray-400 text-sm">
              {isSignIn ? 'Welcome back to FBM' : "Join Cambodia's car community"}
            </p>
          </div>

          {/* Tab Toggle */}
          <div className="flex border-b border-line">
            <button
              onClick={() => { setIsSignIn(true); setError(''); setSuccess('') }}
              className={`flex-1 py-3 text-sm font-semibold transition-all ${
                isSignIn
                  ? 'text-brand border-b-2 border-brand'
                  : 'text-muted hover:text-gray-700'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsSignIn(false); setError(''); setSuccess('') }}
              className={`flex-1 py-3 text-sm font-semibold transition-all ${
                !isSignIn
                  ? 'text-brand border-b-2 border-brand'
                  : 'text-muted hover:text-gray-700'
              }`}
            >
              Sign Up
            </button>
          </div>

          {/* Form */}
          <div className="p-8">
            {error && (
              <div className="mb-5 p-4 bg-red-50 border border-red-100 rounded-xl">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}
            {success && (
              <div className="mb-5 p-4 bg-emerald-50 border border-emerald-100 rounded-xl">
                <p className="text-sm text-emerald-700">{success}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {!isSignIn && (
                <Input
                  label="Full Name"
                  type="text"
                  placeholder="Sophea Rin"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required={!isSignIn}
                />
              )}

              <Input
                label="Email Address"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-ink">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    placeholder={isSignIn ? 'Your password' : 'Min. 8 characters'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={isSignIn ? undefined : 8}
                    className="w-full px-4 py-2.5 pr-10 rounded-xl border border-line text-ink bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand placeholder:text-gray-400"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-3 flex items-center text-gray-400 hover:text-muted"
                  >
                    {showPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>

              {isSignIn && (
                <div className="text-right">
                  <button type="button" className="text-xs text-brand hover:underline">
                    Forgot password?
                  </button>
                </div>
              )}

              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                disabled={loading}
              >
                {loading
                  ? 'Please wait...'
                  : isSignIn
                  ? 'Sign In'
                  : 'Create Account'}
              </Button>
            </form>

            <div className="mt-6 pt-6 border-t border-line text-center">
              <p className="text-sm text-muted">
                {isSignIn ? "Don't have an account? " : 'Already have an account? '}
                <button
                  onClick={() => { setIsSignIn(!isSignIn); setError(''); setSuccess('') }}
                  className="font-semibold text-brand hover:underline"
                >
                  {isSignIn ? 'Sign Up' : 'Sign In'}
                </button>
              </p>
            </div>
          </div>
        </div>

        <p className="text-xs text-center text-gray-400 mt-6">
          By signing in, you agree to FBM&apos;s Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  )
}
