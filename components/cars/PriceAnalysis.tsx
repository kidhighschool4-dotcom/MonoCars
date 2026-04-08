import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import type { PriceAnalysis as PriceAnalysisType } from '@/types'
import Badge from '@/components/ui/Badge'

interface PriceAnalysisProps {
  analysis: PriceAnalysisType
}

export default function PriceAnalysis({ analysis }: PriceAnalysisProps) {
  const { estimatedValue, askingPrice, difference, label, confidence } = analysis

  const isGoodDeal = label === 'Good Deal'
  const isOverpriced = label === 'Overpriced'

  const meterPosition = Math.min(
    95,
    Math.max(5, (askingPrice / estimatedValue) * 50)
  )

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <div className="flex items-center justify-between mb-5">
        <h3 className="font-bold text-[#1A1A1A] text-lg">Price Analysis</h3>
        <Badge label={label} />
      </div>

      {/* Gauge Meter */}
      <div className="mb-6">
        <div className="relative h-4 bg-gradient-to-r from-emerald-400 via-amber-400 to-red-500 rounded-full overflow-visible mb-3">
          {/* Marker */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-5 h-5 bg-white border-2 border-[#1A1A1A] rounded-full shadow-lg transition-all duration-700"
            style={{ left: `${meterPosition}%`, transform: 'translateY(-50%) translateX(-50%)' }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500">
          <span>Great Deal</span>
          <span>Fair Value</span>
          <span>Overpriced</span>
        </div>
      </div>

      {/* Price Comparison */}
      <div className="grid grid-cols-2 gap-4 mb-5">
        <div className="bg-gray-50 rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Asking Price</p>
          <p className="text-xl font-black text-[#1A1A1A]">
            ${askingPrice.toLocaleString()}
          </p>
        </div>
        <div className="bg-gray-50 rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Est. Market Value</p>
          <p className="text-xl font-black text-[#CBA135]">
            ${estimatedValue.toLocaleString()}
          </p>
        </div>
      </div>

      {/* Difference */}
      <div
        className={`flex items-center justify-between p-4 rounded-xl ${
          isGoodDeal
            ? 'bg-emerald-50 border border-emerald-100'
            : isOverpriced
            ? 'bg-red-50 border border-red-100'
            : 'bg-amber-50 border border-amber-100'
        }`}
      >
        <div className="flex items-center gap-2">
          {isGoodDeal ? (
            <TrendingDown className="w-5 h-5 text-emerald-600" />
          ) : isOverpriced ? (
            <TrendingUp className="w-5 h-5 text-red-600" />
          ) : (
            <Minus className="w-5 h-5 text-amber-600" />
          )}
          <span className={`text-sm font-semibold ${
            isGoodDeal ? 'text-emerald-700' : isOverpriced ? 'text-red-700' : 'text-amber-700'
          }`}>
            {isGoodDeal
              ? `$${Math.abs(difference).toLocaleString()} below market`
              : isOverpriced
              ? `$${Math.abs(difference).toLocaleString()} above market`
              : 'At fair market value'}
          </span>
        </div>
        <span className="text-xs text-gray-500">{confidence}% confidence</span>
      </div>
    </div>
  )
}
