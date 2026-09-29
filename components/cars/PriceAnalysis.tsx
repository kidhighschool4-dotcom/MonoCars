import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import clsx from 'clsx'
import type { PriceAnalysis as PriceAnalysisType } from '@/types'
import Badge from '@/components/ui/Badge'

interface PriceAnalysisProps {
  analysis: PriceAnalysisType
}

export default function PriceAnalysis({ analysis }: PriceAnalysisProps) {
  const { estimatedValue, askingPrice, difference, label, confidence } = analysis

  const isGoodDeal = label === 'Good Deal'
  const isOverpriced = label === 'Overpriced'

  // Centre of the bar = market value. ratio 0.5 → 0%, 1.0 → 50%, 1.5 → 100%
  const ratio = askingPrice / estimatedValue
  const meterPosition = Math.min(96, Math.max(4, (ratio - 0.5) * 100))

  const tone = isGoodDeal
    ? { box: 'bg-emerald-50 text-emerald-800', Icon: TrendingDown, text: `$${Math.abs(difference).toLocaleString()} below market value` }
    : isOverpriced
    ? { box: 'bg-rose-50 text-rose-800', Icon: TrendingUp, text: `$${Math.abs(difference).toLocaleString()} above market value` }
    : { box: 'bg-sky-50 text-sky-800', Icon: Minus, text: 'Priced around market value' }

  return (
    <div className="bg-surface rounded-3xl border border-line p-6">
      <div className="flex items-center justify-between gap-3 mb-6">
        <h2 className="font-semibold text-ink text-lg">AI price check</h2>
        <Badge label={label} size="sm" />
      </div>

      <div className="mb-6">
        <div className="relative h-2.5 rounded-full bg-gradient-to-r from-emerald-400 via-sky-400 to-rose-400">
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-5 bg-ink/20 rounded" aria-hidden="true" />
          <span
            className="absolute top-1/2 w-5 h-5 rounded-full bg-white ring-[3px] ring-ink shadow-md transition-all duration-700"
            style={{ left: `${meterPosition}%`, transform: 'translate(-50%, -50%)' }}
            aria-hidden="true"
          />
        </div>
        <div className="mt-2.5 flex justify-between text-xs text-muted">
          <span>Below market</span>
          <span>Fair</span>
          <span>Above market</span>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-2xl bg-paper p-4">
          <dt className="text-xs text-muted">Asking price</dt>
          <dd className="text-xl font-semibold text-ink mt-1 tnum">${askingPrice.toLocaleString()}</dd>
        </div>
        <div className="rounded-2xl bg-brand-soft p-4">
          <dt className="text-xs text-brand">Market value</dt>
          <dd className="text-xl font-semibold text-brand mt-1 tnum">${estimatedValue.toLocaleString()}</dd>
        </div>
      </dl>

      <div className={clsx('flex items-center justify-between gap-3 rounded-2xl px-4 py-3.5', tone.box)}>
        <span className="flex items-center gap-2 text-sm font-semibold">
          <tone.Icon className="w-4 h-4" />
          {tone.text}
        </span>
        <span className="text-xs opacity-70 tnum whitespace-nowrap">{confidence}% sure</span>
      </div>

      <p className="mt-4 text-xs text-muted leading-relaxed">
        Estimated from make, model, year and mileage against the Cambodian market. Use it as a guide when you negotiate.
      </p>
    </div>
  )
}
