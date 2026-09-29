import Link from 'next/link'
import { MapPin, ArrowUpRight } from 'lucide-react'
import type { Car } from '@/types'
import Badge from '@/components/ui/Badge'
import SafeImage from '@/components/ui/SafeImage'

interface CarCardProps {
  car: Car
}

const KHR_PER_USD = 4100

export default function CarCard({ car }: CarCardProps) {
  const title = `${car.make} ${car.model}`
  const specs = [
    String(car.year),
    `${car.mileage.toLocaleString()} km`,
    car.transmission ?? car.fuel ?? car.type,
  ].filter(Boolean)

  return (
    <Link
      href={`/cars/${car.id}`}
      data-testid="listing-card"
      data-listing-id={car.id}
      aria-label={`${car.year} ${title}`}
      className="group block bg-surface rounded-2xl border border-line overflow-hidden hover:border-brand-tint hover:shadow-[0_12px_40px_-12px_rgba(20,34,79,0.18)] transition-all duration-300"
    >
      {/* Image */}
      <div className="relative aspect-[4/3] overflow-hidden bg-paper">
        <SafeImage
          src={car.images[0]}
          alt={`${car.year} ${title}`}
          loading="lazy"
          className="w-full h-full object-cover group-hover:scale-[1.04] transition-transform duration-500"
        />
        <div className="absolute top-3 left-3">
          <Badge label={car.priceLabel} size="sm" className="bg-white/95 backdrop-blur" />
        </div>
        <span className="absolute top-3 right-3 w-9 h-9 rounded-full bg-white/95 text-ink flex items-center justify-center opacity-0 translate-y-1 group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-300">
          <ArrowUpRight className="w-4 h-4" />
        </span>
      </div>

      {/* Content */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-semibold text-ink text-lg leading-snug truncate">{title}</h3>
            <p className="text-sm text-muted mt-1 tnum">{specs.join(' · ')}</p>
          </div>
          <span className="text-xs font-medium text-muted bg-paper px-2.5 py-1 rounded-full flex-shrink-0">
            {car.type}
          </span>
        </div>

        <div className="mt-4 pt-4 border-t border-line flex items-end justify-between gap-3">
          <div>
            <p className="text-2xl font-bold text-ink tracking-tight tnum">${car.price.toLocaleString()}</p>
            <p className="text-xs text-subtle mt-0.5 tnum">≈ ៛{(car.price * KHR_PER_USD).toLocaleString()}</p>
          </div>
          <p className="flex items-center gap-1 text-sm text-muted">
            <MapPin className="w-3.5 h-3.5" />
            {car.location}
          </p>
        </div>
      </div>
    </Link>
  )
}
