'use client'

import { useState } from 'react'
import { supabase } from '@/lib/supabase'
import { useAuth } from '@/lib/auth-context'

interface Props {
  to: 'customer' | 'seller'
  label: string
  variant?: 'primary' | 'outline'
}

/** Switches the signed-in user's account type. RLS only allows 'customer' or 'seller' on their own row. */
export default function SwitchRoleButton({ to, label, variant = 'primary' }: Props) {
  const { user, refreshProfile } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const onClick = async () => {
    if (!user) return
    setBusy(true)
    setError('')
    const { error: e } = await supabase.from('profiles').update({ role: to }).eq('id', user.id)
    if (e) setError('Could not switch account type. Please try again.')
    else await refreshProfile()
    setBusy(false)
  }

  return (
    <div>
      <button
        type="button"
        onClick={onClick}
        disabled={busy || !user}
        className={
          variant === 'primary'
            ? 'w-full py-3.5 rounded-full bg-brand text-white font-semibold hover:bg-brand-strong transition-colors disabled:opacity-60'
            : 'px-5 py-2.5 rounded-full border border-line text-ink text-sm font-semibold hover:border-ink transition-colors disabled:opacity-60'
        }
      >
        {busy ? 'Switching…' : label}
      </button>
      {error && <p className="text-sm text-rose-600 mt-2">{error}</p>}
    </div>
  )
}
