import { notFound } from 'next/navigation'
import Link from 'next/link'
import { MapPin, Gauge, Calendar, Phone, CheckCircle, XCircle, ArrowLeft, Car } from 'lucide-react'
import { getCar, getRelatedCars } from '@/lib/db'
import { getPriceAnalysis } from '@/lib/priceEstimation'
import PriceAnalysis from '@/components/cars/PriceAnalysis'
import CarCard from '@/components/cars/CarCard'
import Badge from '@/components/ui/Badge'
import ImageGallery from '@/components/cars/ImageGallery'
import MessageSellerButton from '@/components/chat/MessageSellerButton'

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function CarDetailPage({ params }: PageProps) {
  const { id } = await params
  const [car, related] = await Promise.all([
    getCar(id),
    getRelatedCars(id, '', 3).catch(() => []),
  ])

  if (!car) notFound()

  const analysis = getPriceAnalysis(car)
  const relatedCars = related.length
    ? related
    : await getRelatedCars(id, car.type, 3)

  return (
    <div className="min-h-screen bg-[#F8F5F0]">
      {/* Back nav */}
      <div className="bg-white border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <Link
            href="/cars"
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#1A1A1A] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Listings
          </Link>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Image Gallery */}
            <ImageGallery
              images={car.images}
              alt={`${car.year} ${car.make} ${car.model}`}
            />

            {/* Car Details */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div>
                  <h1 className="text-2xl md:text-3xl font-black text-[#1A1A1A]">
                    {car.year} {car.make} {car.model}
                  </h1>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge label={car.priceLabel} />
                    <span className="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full font-medium">
                      {car.type}
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-black text-[#CBA135]">
                    ${car.price.toLocaleString()}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">≈ ៛{(car.price * 4100).toLocaleString()}</p>
                </div>
              </div>

              {/* Specs Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6 p-4 bg-gray-50 rounded-xl">
                {[
                  { icon: Calendar, label: 'Year', value: car.year.toString() },
                  { icon: Gauge, label: 'Mileage', value: `${car.mileage.toLocaleString()} km` },
                  { icon: MapPin, label: 'Location', value: car.location },
                  { icon: Car, label: 'Type', value: car.type },
                ].map(({ icon: Icon, label, value }) => (
                  <div key={label} className="text-center">
                    <div className="flex justify-center mb-1">
                      <Icon className="w-4 h-4 text-[#CBA135]" />
                    </div>
                    <p className="text-xs text-gray-400 mb-0.5">{label}</p>
                    <p className="text-sm font-semibold text-[#1A1A1A]">{value}</p>
                  </div>
                ))}
              </div>

              {/* Description */}
              <p className="text-gray-600 text-sm leading-relaxed">{car.description}</p>
            </div>

            {/* Pros & Cons */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <h2 className="font-bold text-[#1A1A1A] text-lg mb-5">Pros &amp; Cons</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div>
                  <h3 className="font-semibold text-emerald-700 text-sm uppercase tracking-wide mb-3 flex items-center gap-1.5">
                    <CheckCircle className="w-4 h-4" /> Pros
                  </h3>
                  <ul className="space-y-2">
                    {car.pros.map((pro, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                        <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                        {pro}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="font-semibold text-red-700 text-sm uppercase tracking-wide mb-3 flex items-center gap-1.5">
                    <XCircle className="w-4 h-4" /> Cons
                  </h3>
                  <ul className="space-y-2">
                    {car.cons.map((con, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                        <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                        {con}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Price Analysis */}
            <PriceAnalysis analysis={analysis} />

            {/* Seller Info */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <h3 className="font-bold text-[#1A1A1A] text-lg mb-5">Contact Seller</h3>
              <div className="flex items-center gap-3 mb-5">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#CBA135] to-[#7A1E1E] flex items-center justify-center">
                  <span className="text-white font-bold text-base">
                    {car.sellerName.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)}
                  </span>
                </div>
                <div>
                  <p className="font-semibold text-[#1A1A1A]">{car.sellerName}</p>
                  <p className="text-xs text-gray-400">Verified Seller</p>
                </div>
              </div>

              {car.sellerId && (
                <MessageSellerButton carId={car.id} sellerId={car.sellerId} />
              )}
              {/* Call button */}
              <a
                href={`tel:${car.sellerPhone.replace(/\s/g, '')}`}
                className="flex items-center justify-center gap-2 w-full py-3 bg-[#CBA135] text-[#1A1A1A] font-bold rounded-xl hover:bg-[#b8922e] transition-colors text-sm mb-2"
              >
                <Phone className="w-4 h-4" />
                Call: {car.sellerPhone}
              </a>
              {/* WhatsApp button */}
              <a
                href={`https://wa.me/${car.sellerPhone.replace(/[\s+]/g, '')}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-3 bg-[#25D366] text-white font-bold rounded-xl hover:bg-[#22c55e] transition-colors text-sm mb-2"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                </svg>
                WhatsApp
              </a>
              {/* Telegram button */}
              <a
                href={`https://t.me/${car.sellerPhone.replace(/[\s+]/g, '')}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-3 bg-[#2AABEE] text-white font-bold rounded-xl hover:bg-[#0088cc] transition-colors text-sm"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.96 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                </svg>
                Telegram
              </a>

              <p className="text-xs text-gray-400 text-center mt-3">
                Available Mon–Sat, 8am–6pm
              </p>
            </div>

            {/* Source info */}
            <div className="bg-amber-50 border border-amber-100 rounded-2xl p-4">
              <p className="text-xs text-amber-800 leading-relaxed">
                <span className="font-semibold">Price Transparency:</span> Our AI estimates market
                value based on make, model, year, and mileage. Use this as a guide in negotiations.
              </p>
            </div>
          </div>
        </div>

        {/* Related Cars */}
        {relatedCars.length > 0 && (
          <section className="mt-12">
            <h2 className="text-2xl font-black text-[#1A1A1A] mb-6">Similar {car.type}s</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {relatedCars.map((relatedCar) => (
                <CarCard key={relatedCar.id} car={relatedCar} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
