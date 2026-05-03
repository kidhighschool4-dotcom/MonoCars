'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { MessageCircle } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'

interface Props {
  carId: string
  sellerId: string
}

export default function MessageSellerButton({ carId, sellerId }: Props) {
  const router = useRouter()
  const { user, loading } = useAuth()
  const [busy, setBusy] = useState(false)

  if (loading) return null
  if (user?.id === sellerId) return null

  const handleClick = async () => {
    if (!user) {
      router.push(`/auth?next=/cars/${carId}`)
      return
    }
    setBusy(true)
    try {
      const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ carId, sellerId }),
      })
      if (!res.ok) throw new Error()
      const { id } = await res.json()
      router.push(`/messages/${id}`)
    } catch {
      setBusy(false)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      className="flex items-center justify-center gap-2 w-full py-3 bg-[#1A1A1A] text-white font-bold rounded-xl hover:bg-[#2a2a2a] transition-colors text-sm mb-2 disabled:opacity-60"
    >
      <MessageCircle className="w-4 h-4" />
      {busy ? 'Opening chat...' : 'Message Seller'}
    </button>
  )
}
