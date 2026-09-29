'use client'

import { useState } from 'react'
import { Heart, MessageCircle, Send } from 'lucide-react'
import type { Post } from '@/types'

interface PostCardProps {
  post: Post
}

function timeAgo(dateString: string): string {
  const now = new Date()
  const date = new Date(dateString)
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  if (days < 30) return `${Math.floor(days / 7)} weeks ago`
  return `${Math.floor(days / 30)} months ago`
}

const typeConfig = {
  question: { label: 'Question', color: 'bg-blue-100 text-blue-800' },
  photo: { label: 'Photo', color: 'bg-purple-100 text-purple-800' },
  discussion: { label: 'Discussion', color: 'bg-amber-100 text-brand-deep' },
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

export default function PostCard({ post }: PostCardProps) {
  const [liked, setLiked] = useState(false)
  const [likeCount, setLikeCount] = useState(post.likes)
  const [showComments, setShowComments] = useState(false)
  const [commentText, setCommentText] = useState('')

  const typeInfo = typeConfig[post.type]

  const handleLike = () => {
    setLiked(!liked)
    setLikeCount(liked ? likeCount - 1 : likeCount + 1)
  }

  const handleComment = (e: React.FormEvent) => {
    e.preventDefault()
    setCommentText('')
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-line p-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand to-brand-deep flex items-center justify-center flex-shrink-0">
            <span className="text-white font-bold text-sm">{getInitials(post.userName)}</span>
          </div>
          <div>
            <p className="font-semibold text-ink text-sm">{post.userName}</p>
            <p className="text-xs text-gray-400">{timeAgo(post.createdAt)}</p>
          </div>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${typeInfo.color}`}>
          {typeInfo.label}
        </span>
      </div>

      {/* Content */}
      <p className="text-gray-700 text-sm leading-relaxed mb-4">{post.content}</p>

      {/* Images */}
      {post.images.length > 0 && (
        <div className={`grid gap-2 mb-4 ${post.images.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {post.images.map((img, idx) => (
            <div key={idx} className="rounded-xl overflow-hidden aspect-video bg-gray-100">
              <img
                src={img}
                alt={`Post image ${idx + 1}`}
                className="w-full h-full object-cover"
              />
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-4 pt-3 border-t border-gray-50">
        <button
          onClick={handleLike}
          className="flex items-center gap-1.5 text-sm text-muted hover:text-brand-deep transition-colors group"
        >
          <Heart
            className={`w-4 h-4 transition-all ${
              liked ? 'fill-brand-deep text-brand-deep' : 'group-hover:scale-110'
            }`}
          />
          <span className={liked ? 'text-brand-deep font-medium' : ''}>{likeCount}</span>
        </button>
        <button
          onClick={() => setShowComments(!showComments)}
          className="flex items-center gap-1.5 text-sm text-muted hover:text-brand transition-colors"
        >
          <MessageCircle className="w-4 h-4" />
          <span>{post.comments.length}</span>
        </button>
      </div>

      {/* Comments */}
      {showComments && (
        <div className="mt-4 space-y-3">
          {post.comments.map((comment) => (
            <div key={comment.id} className="flex gap-2.5">
              <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                <span className="text-muted font-semibold text-xs">
                  {getInitials(comment.userName)}
                </span>
              </div>
              <div className="bg-paper rounded-xl px-3 py-2 flex-1">
                <p className="font-semibold text-xs text-ink mb-0.5">{comment.userName}</p>
                <p className="text-xs text-muted leading-relaxed">{comment.content}</p>
              </div>
            </div>
          ))}

          {/* Comment Input */}
          <form onSubmit={handleComment} className="flex gap-2 mt-2">
            <input
              type="text"
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Write a comment..."
              className="flex-1 text-sm px-3 py-2 rounded-xl border border-line focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand"
            />
            <button
              type="submit"
              className="p-2 bg-brand text-white rounded-xl hover:bg-brand-strong transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
