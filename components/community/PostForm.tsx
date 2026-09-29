'use client'

import { useState } from 'react'
import { MessageSquare, Image, HelpCircle } from 'lucide-react'
import Button from '@/components/ui/Button'
import { useAuth } from '@/lib/auth-context'
import Link from 'next/link'

export default function PostForm() {
  const { user } = useAuth()
  const [content, setContent] = useState('')
  const [type, setType]       = useState<'question' | 'photo' | 'discussion'>('discussion')
  const [status, setStatus]   = useState<'idle' | 'loading' | 'success' | 'error'>('idle')

  if (!user) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-line p-6 text-center">
        <div className="w-12 h-12 rounded-full bg-brand-soft flex items-center justify-center mx-auto mb-3">
          <MessageSquare className="w-6 h-6 text-brand" />
        </div>
        <h3 className="font-semibold text-ink mb-1">Join the conversation</h3>
        <p className="text-sm text-muted mb-4">
          Sign in to share your thoughts, ask questions, and connect with fellow car enthusiasts.
        </p>
        <Link href="/auth?next=/community">
          <Button variant="primary" size="md">Sign In to Post</Button>
        </Link>
      </div>
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!content.trim() || status === 'loading') return
    setStatus('loading')
    try {
      const res = await fetch('/api/community/posts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, post_type: type }),
      })
      if (!res.ok) throw new Error()
      setContent('')
      setStatus('success')
      setTimeout(() => setStatus('idle'), 3000)
    } catch {
      setStatus('error')
      setTimeout(() => setStatus('idle'), 3000)
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-line p-5">
      <h3 className="font-semibold text-ink mb-4">Share with the Community</h3>

      {/* Type Selector */}
      <div className="flex gap-2 mb-4">
        {([
          { value: 'discussion', label: 'Discussion', icon: MessageSquare },
          { value: 'question',   label: 'Question',   icon: HelpCircle },
          { value: 'photo',      label: 'Photo',       icon: Image },
        ] as const).map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => setType(value)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              type === value
                ? 'bg-brand text-white'
                : 'bg-paper text-muted hover:bg-gray-100'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit}>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Share a photo, ask a question, or start a discussion..."
          rows={3}
          className="w-full px-4 py-3 rounded-xl border border-line text-sm text-ink placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand resize-none mb-3"
        />

        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-400">{content.length} / 1000</p>
          <button
            type="submit"
            disabled={!content.trim() || status === 'loading' || content.length > 1000}
            className="px-5 py-2 bg-brand text-white font-semibold rounded-xl text-sm hover:bg-brand-strong disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {status === 'loading' ? 'Posting...' : 'Post'}
          </button>
        </div>

        {status === 'success' && (
          <p className="text-xs text-green-600 font-medium mt-2">Posted! Refresh to see your post.</p>
        )}
        {status === 'error' && (
          <p className="text-xs text-red-500 mt-2">Failed to post. Please try again.</p>
        )}
      </form>
    </div>
  )
}
