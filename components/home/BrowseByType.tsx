import Link from 'next/link'
import { ArrowUpRight } from 'lucide-react'
import SectionHeading from '@/components/ui/SectionHeading'

const types = [
  { name: 'SUV',           note: 'Family & rainy season',  img: 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=900&q=75' },
  { name: 'Sedan',         note: 'City & daily driving',   img: 'https://images.unsplash.com/photo-1550355291-bbee04a92027?w=900&q=75' },
  { name: 'Pickup',        note: 'Work & provinces',       img: 'https://images.unsplash.com/photo-1559416523-140ddc3d238c?w=900&q=75' },
  { name: 'MPV (Minivan)', label: 'Minivan', note: 'Big families & business', img: 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=900&q=75' },
]

export default function BrowseByType() {
  return (
    <section className="py-20 md:py-28 bg-surface border-y border-line">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <SectionHeading eyebrow="Browse by type" title="What are you looking for?" />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5">
          {types.map((t) => (
            <Link
              key={t.name}
              href={`/cars?carType=${encodeURIComponent(t.name)}`}
              className="group relative aspect-[4/5] rounded-3xl overflow-hidden bg-ink"
            >
              <img
                src={t.img}
                alt=""
                loading="lazy"
                className="absolute inset-0 w-full h-full object-cover opacity-80 group-hover:opacity-100 group-hover:scale-105 transition-all duration-500"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-ink/90 via-ink/20 to-transparent" />
              <span className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/15 backdrop-blur text-white flex items-center justify-center group-hover:bg-brand transition-colors">
                <ArrowUpRight className="w-5 h-5" />
              </span>
              <div className="absolute bottom-0 inset-x-0 p-5 md:p-6 text-white">
                <p className="text-2xl md:text-3xl font-semibold tracking-tight">{t.label ?? t.name}</p>
                <p className="text-sm text-white/70 mt-1">{t.note}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}
