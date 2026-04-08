'use client'

import { useState } from 'react'
import { MessageSquare, Image, HelpCircle } from 'lucide-react'
import Button from '@/components/ui/Button'

interface PostFormProps {
  isAuthenticated?: boolean
}

export default function PostForm({ isAuthenticated = false }: PostFormProps) {
  const [content, setContent] = useState('')
  const [type, setType] = useState<'question' | 'photo' | 'discussion'>('discussion')
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!content.trim()) return
    setSubmitted(true)
    setContent('')
    setTimeout(() => setSubmitted(false), 3000)
  }

  if (!isAuthenticated) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 text-center">
        <div className="w-12 h-12 rounded-full bg-amber-50 flex items-center justify-center mx-auto mb-3">
          <MessageSquare className="w-6 h-6 text-[#CBA135]" />
        </div>
        <h3 className="font-semibold text-[#1A1A1A] mb-1">Join the conversation</h3>
        <p className="text-sm text-gray-500 mb-4">
          Sign in to share your thoughts, ask questions, and connect with fellow car enthusiasts.
        </p>
        <Button variant="primary" size="md">
          Sign In to Post
        </Button>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <h3 className="font-semibold text-[#1A1A1A] mb-4">Share with the Community</h3>

      {/* Type Selector */}
      <div className="flex gap-2 mb-4">
        {(
          [
            { value: 'discussion', label: 'Discussion', icon: MessageSquare },
            { value: 'question', label: 'Question', icon: HelpCircle },
            { value: 'photo', label: 'Photo', icon: Image },
          ] as const
        ).map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            onClick={() => setType(value)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              type === value
                ? 'bg-[#CBA135] text-[#1A1A1A]'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
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
          placeholder={
            type === 'question'
              ? 'Ask the community a question about cars...'
              : type === 'photo'
              ? 'Share a photo and caption...'
              : 'Start a discussion about cars in Cambodia...'
          }
          rows={3}
          className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm text-[#1A1A1A] focus:outline-none focus:ring-2 focus:ring-[#CBA135] focus:border-[#CBA135] resize-none placeholder:text-gray-400 mb-3"
        />

        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">{content.length} / 500</span>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!content.trim() || content.length > 500}
          >
            {submitted ? 'Posted!' : 'Post'}
          </Button>
        </div>
      </form>
    </div>
  )
}
