import Link from 'next/link'
import { MapPin, Gauge } from 'lucide-react'
import type { Car } from '@/types'
import Badge from '@/components/ui/Badge'

interface CarCardProps {
  car: Car
}

export default function CarCard({ car }: CarCardProps) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden group hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
      {/* Image */}
      <div className="relative aspect-video overflow-hidden bg-gray-100">
        <img
          src={car.images[0]}
          alt={`${car.year} ${car.make} ${car.model}`}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        />
        {/* Price Label Badge */}
        <div className="absolute top-3 left-3">
          <Badge label={car.priceLabel} size="sm" />
        </div>
        {/* Source badge */}
        {car.source === 'scraped' && (
          <div className="absolute top-3 right-3">
            <span className="bg-[#1A1A1A]/70 text-white text-xs px-2 py-0.5 rounded-full backdrop-blur-sm">
              Featured
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Title row */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="font-bold text-[#1A1A1A] text-base leading-tight">
            {car.year} {car.make} {car.model}
          </h3>
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full flex-shrink-0">
            {car.type}
          </span>
        </div>

        {/* Price */}
        <div className="mb-3">
          <p className="text-2xl font-black text-[#CBA135]">
            ${car.price.toLocaleString()}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">≈ ៛{(car.price * 4100).toLocaleString()}</p>
        </div>

        {/* Details */}
        <div className="flex items-center gap-4 text-xs text-gray-500 mb-4">
          <div className="flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-[#CBA135]" />
            <span>{car.location}</span>
          </div>
          <div className="flex items-center gap-1">
            <Gauge className="w-3.5 h-3.5 text-[#CBA135]" />
            <span>{car.mileage.toLocaleString()} km</span>
          </div>
        </div>

        {/* Action */}
        <Link
          href={`/cars/${car.id}`}
          className="block w-full text-center py-2.5 px-4 bg-[#1A1A1A] text-white text-sm font-semibold rounded-xl hover:bg-[#CBA135] hover:text-[#1A1A1A] transition-all duration-200"
        >
          View Details
        </Link>
      </div>
    </div>
  )
}
