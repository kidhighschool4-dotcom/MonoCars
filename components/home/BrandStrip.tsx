import Link from 'next/link'

const makes = ['Toyota', 'Lexus', 'Ford', 'Hyundai', 'Mazda', 'Honda', 'Mercedes-Benz', 'BMW', 'Kia', 'Mitsubishi', 'Nissan', 'Land Rover']

export default function BrandStrip() {
  // Rendered twice so the marquee loops seamlessly
  const loop = [...makes, ...makes]
  return (
    <section className="bg-ink border-t border-ink-3 py-7 overflow-hidden" aria-label="Popular makes">
      <div className="flex w-max fbm-marquee hover:[animation-play-state:paused]">
        {loop.map((make, i) => (
          <Link
            key={`${make}-${i}`}
            href="/cars"
            aria-hidden={i >= makes.length}
            tabIndex={i >= makes.length ? -1 : undefined}
            className="px-8 md:px-12 text-xl md:text-2xl font-semibold tracking-tight text-white/35 hover:text-white transition-colors whitespace-nowrap"
          >
            {make}
          </Link>
        ))}
      </div>
    </section>
  )
}
