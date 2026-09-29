import { notFound } from 'next/navigation'
import Link from 'next/link'
import { MapPin, Gauge, Calendar, Phone, Check, X, ArrowLeft, Car, Fuel, Cog, ShieldCheck } from 'lucide-react'
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

const KHR_PER_USD = 4100

export default async function CarDetailPage({ params }: PageProps) {
  const { id } = await params
  const car = await getCar(id)
  if (!car) notFound()

  const analysis = getPriceAnalysis(car)
  const relatedCars = await getRelatedCars(id, car.type, 3)
  const phone = car.sellerPhone.replace(/[\s+]/g, '')

  const specs = [
    { icon: Calendar, label: 'Year', value: String(car.year) },
    { icon: Gauge, label: 'Mileage', value: `${car.mileage.toLocaleString()} km` },
    { icon: Car, label: 'Body type', value: car.type },
    { icon: MapPin, label: 'Location', value: car.location },
    ...(car.fuel ? [{ icon: Fuel, label: 'Fuel', value: car.fuel }] : []),
    ...(car.transmission ? [{ icon: Cog, label: 'Gearbox', value: car.transmission }] : []),
  ]

  const initials = car.sellerName.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)

  return (
    <div className="min-h-screen">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-16 md:pb-24">
        <Link
          href="/cars"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          All cars
        </Link>

        {/* Title row */}
        <div className="mt-5 mb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Badge label={car.priceLabel} size="sm" />
              <span className="text-xs font-medium text-muted bg-surface border border-line px-2.5 py-1 rounded-full">{car.type}</span>
            </div>
            <h1 className="text-3xl md:text-5xl font-semibold tracking-tight text-ink">
              {car.year} {car.make} {car.model}
            </h1>
            <p className="mt-2 flex items-center gap-1.5 text-muted">
              <MapPin className="w-4 h-4" /> {car.location}
            </p>
          </div>
          <div className="md:text-right">
            <p className="text-4xl md:text-5xl font-semibold tracking-tight text-ink tnum">${car.price.toLocaleString()}</p>
            <p className="text-sm text-muted mt-1 tnum">≈ ៛{(car.price * KHR_PER_USD).toLocaleString()}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
          {/* Main */}
          <div className="lg:col-span-2 space-y-6">
            <ImageGallery images={car.images} alt={`${car.year} ${car.make} ${car.model}`} />

            {/* Specs */}
            <section className="bg-surface rounded-3xl border border-line p-6 md:p-8">
              <h2 className="font-semibold text-ink text-lg mb-5">Key details</h2>
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
                {specs.map(({ icon: Icon, label, value }) => (
                  <div key={label} className="flex items-start gap-3">
                    <span className="w-10 h-10 rounded-xl bg-paper flex items-center justify-center flex-shrink-0">
                      <Icon className="w-5 h-5 text-muted" />
                    </span>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted">{label}</dt>
                      <dd className="font-semibold text-ink truncate">{value}</dd>
                    </div>
                  </div>
                ))}
              </dl>

              <div className="mt-8 pt-6 border-t border-line">
                <h2 className="font-semibold text-ink text-lg mb-3">About this car</h2>
                <p className="text-muted text-[17px] leading-relaxed">{car.description}</p>
              </div>
            </section>

            {/* Pros & cons */}
            {(car.pros.length > 0 || car.cons.length > 0) && (
              <section className="grid sm:grid-cols-2 gap-4">
                <div className="bg-surface rounded-3xl border border-line p-6">
                  <h2 className="font-semibold text-ink mb-4">What&apos;s good</h2>
                  <ul className="space-y-3">
                    {car.pros.map((pro, idx) => (
                      <li key={idx} className="flex items-start gap-3 text-ink/80">
                        <span className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <Check className="w-3 h-3" />
                        </span>
                        {pro}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="bg-surface rounded-3xl border border-line p-6">
                  <h2 className="font-semibold text-ink mb-4">Worth knowing</h2>
                  <ul className="space-y-3">
                    {car.cons.map((con, idx) => (
                      <li key={idx} className="flex items-start gap-3 text-ink/80">
                        <span className="w-5 h-5 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <X className="w-3 h-3" />
                        </span>
                        {con}
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
            )}
          </div>

          {/* Sidebar */}
          <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
            <div className="bg-surface rounded-3xl border border-line p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 rounded-full bg-ink flex items-center justify-center">
                  <span className="text-white font-semibold">{initials}</span>
                </div>
                <div>
                  <p className="font-semibold text-ink">{car.sellerName}</p>
                  <p className="flex items-center gap-1 text-sm text-muted">
                    <ShieldCheck className="w-4 h-4 text-brand" /> Verified seller
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                {car.sellerId && <MessageSellerButton carId={car.id} sellerId={car.sellerId} />}
                <a
                  href={`tel:${car.sellerPhone.replace(/\s/g, '')}`}
                  className="flex items-center justify-center gap-2 w-full py-3.5 rounded-full bg-ink text-white font-semibold hover:bg-brand transition-colors tnum"
                >
                  <Phone className="w-4 h-4" />
                  Call {car.sellerPhone}
                </a>
                <div className="grid grid-cols-2 gap-2">
                  <a
                    href={`https://t.me/${phone}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 py-3 rounded-full border border-line text-ink font-semibold text-sm hover:border-[#2AABEE] hover:text-[#2AABEE] transition-colors"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.96 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                    </svg>
                    Telegram
                  </a>
                  <a
                    href={`https://wa.me/${phone}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 py-3 rounded-full border border-line text-ink font-semibold text-sm hover:border-[#25D366] hover:text-[#1da851] transition-colors"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                    </svg>
                    WhatsApp
                  </a>
                </div>
              </div>
              <p className="text-xs text-muted text-center mt-4">Usually replies Mon–Sat, 8am–6pm</p>
            </div>

            <PriceAnalysis analysis={analysis} />
          </aside>
        </div>

        {relatedCars.length > 0 && (
          <section className="mt-16 md:mt-24">
            <h2 className="text-2xl md:text-3xl font-semibold tracking-tight text-ink mb-6">More {car.type}s you might like</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
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
