'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, X } from 'lucide-react'

export default function ReviewActions({ listingId, state }: { listingId: string; state: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [error, setError] = useState('')
  const reviewable = state === 'ranked' || state === 'manual_review'

  if (!reviewable) {
    return <span className="text-xs font-medium text-muted bg-paper px-2.5 py-1 rounded-full">{state.replaceAll('_', ' ')}</span>
  }

  const decide = async (decision: 'approve' | 'reject') => {
    setBusy(decision)
    setError('')
    const res = await fetch('/api/admin/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ listingId, decision }),
    })
    if (!res.ok) setError((await res.json().catch(() => ({}))).error ?? 'Failed')
    else router.refresh()
    setBusy(null)
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-2">
        <button onClick={() => decide('approve')} disabled={!!busy}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-full bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-60">
          <Check className="w-3.5 h-3.5" /> {busy === 'approve' ? '…' : 'Approve'}
        </button>
        <button onClick={() => decide('reject')} disabled={!!busy}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-full border border-line text-ink text-xs font-semibold hover:border-rose-500 hover:text-rose-600 disabled:opacity-60">
          <X className="w-3.5 h-3.5" /> {busy === 'reject' ? '…' : 'Reject'}
        </button>
      </div>
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  )
}
