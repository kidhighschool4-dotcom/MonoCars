'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { MessageCircle, ArrowLeft } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'

interface ConvCar {
  id: string
  title: string
  price_usd: number
  car_images: { url: string; is_primary: boolean }[]
}
interface ConvProfile { id: string; full_name: string | null }
interface Conversation {
  id: string
  car_id: string
  buyer_id: string
  seller_id: string
  updated_at: string
  cars: ConvCar
  buyer: ConvProfile
  seller: ConvProfile
  lastMessage?: string
}

export default function MessagesPage() {
  const { user, loading } = useAuth()
  const router = useRouter()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [fetching, setFetching] = useState(true)

  useEffect(() => {
    if (!loading && !user) { router.replace('/auth?next=/messages'); return }
    if (!user) return
    fetch('/api/conversations')
      .then((r) => r.json())
      .then(({ conversations }) => setConversations(conversations ?? []))
      .finally(() => setFetching(false))
  }, [user, loading, router])

  if (loading || fetching) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-paper">
      <div className="bg-ink py-10 md:py-14">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors mb-4">
            <ArrowLeft className="w-4 h-4" /> Back to Home
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight text-white">Messages</h1>
          <p className="text-gray-400 text-sm mt-1">{conversations.length} conversation{conversations.length !== 1 ? 's' : ''}</p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-3">
        {conversations.length === 0 ? (
          <div className="text-center py-20">
            <MessageCircle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-muted font-medium">No messages yet</p>
            <p className="text-gray-400 text-sm mt-1">Browse cars and tap &quot;Message Seller&quot; to start a chat</p>
            <Link href="/cars" className="inline-block mt-5 px-5 py-2.5 bg-brand text-white font-bold rounded-xl text-sm hover:bg-brand-strong transition-colors">
              Browse Cars
            </Link>
          </div>
        ) : (
          conversations.map((conv) => {
            const other = user?.id === conv.buyer_id ? conv.seller : conv.buyer
            const carImage = conv.cars?.car_images?.find((i) => i.is_primary)?.url ?? conv.cars?.car_images?.[0]?.url ?? ''
            const timeAgo = formatRelative(conv.updated_at)
            return (
              <Link key={conv.id} href={`/messages/${conv.id}`}
                className="flex items-center gap-4 bg-white rounded-2xl border border-line shadow-sm p-4 hover:border-brand transition-colors">
                {carImage ? (
                  <img src={carImage} alt={conv.cars?.title} className="w-16 h-16 rounded-xl object-cover flex-shrink-0" />
                ) : (
                  <div className="w-16 h-16 rounded-xl bg-gray-100 flex items-center justify-center flex-shrink-0">
                    <MessageCircle className="w-6 h-6 text-gray-300" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-ink text-sm truncate">{conv.cars?.title ?? 'Car Listing'}</p>
                  <p className="text-xs text-brand font-medium mb-1">${conv.cars?.price_usd?.toLocaleString()}</p>
                  <p className="text-xs text-muted truncate">
                    {other?.full_name ?? 'Unknown'}
                  </p>
                </div>
                <p className="text-xs text-gray-400 flex-shrink-0">{timeAgo}</p>
              </Link>
            )
          })
        )}
      </div>
    </div>
  )
}

function formatRelative(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d`
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
