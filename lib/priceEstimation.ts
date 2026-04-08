import type { PriceAnalysis } from '@/types'

export function estimatePrice(make: string, _model: string, year: number, mileage: number): number {
  const baseValues: Record<string, number> = {
    Toyota: 18000,
    Lexus: 35000,
    BMW: 30000,
    Honda: 15000,
    Hyundai: 14000,
    Kia: 13000,
    Mercedes: 40000,
    Ford: 16000,
  }
  const base = baseValues[make] || 15000
  const ageFactor = Math.max(0.3, 1 - (new Date().getFullYear() - year) * 0.07)
  const mileageFactor = Math.max(0.5, 1 - (mileage / 200000) * 0.4)
  return Math.round(base * ageFactor * mileageFactor)
}

export function getPriceLabel(
  askingPrice: number,
  estimatedValue: number
): 'Good Deal' | 'Fair' | 'Overpriced' {
  const ratio = askingPrice / estimatedValue
  if (ratio < 0.9) return 'Good Deal'
  if (ratio < 1.1) return 'Fair'
  return 'Overpriced'
}

export function getPriceAnalysis(car: {
  price: number
  estimatedValue: number
}): PriceAnalysis {
  const difference = car.estimatedValue - car.price
  const label = getPriceLabel(car.price, car.estimatedValue)
  return {
    estimatedValue: car.estimatedValue,
    askingPrice: car.price,
    difference,
    label,
    confidence: 78,
  }
}
