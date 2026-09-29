import Link from 'next/link'
import { ArrowUpRight, Check } from 'lucide-react'

const sellPoints = ['Free to list', 'Instant AI price estimate', 'Buyers message you directly']

export default function CTASection() {
  return (
    <section className="pb-20 md:pb-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          {/* Sell */}
          <div className="lg:col-span-3 relative overflow-hidden rounded-3xl bg-brand text-white p-8 md:p-12">
            <div className="absolute -right-24 -top-24 w-80 h-80 rounded-full bg-white/10" aria-hidden="true" />
            <div className="absolute right-16 -bottom-32 w-72 h-72 rounded-full bg-brand-deep/40" aria-hidden="true" />
            <div className="relative">
              <p className="text-white/70 text-sm font-medium">For sellers</p>
              <h3 className="mt-3 text-3xl md:text-5xl font-semibold tracking-tight leading-[1.05] max-w-md">
                Sell your car in days, not months.
              </h3>
              <ul className="mt-6 space-y-2.5">
                {sellPoints.map((p) => (
                  <li key={p} className="flex items-center gap-2.5 text-white/90">
                    <span className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center">
                      <Check className="w-3 h-3" />
                    </span>
                    {p}
                  </li>
                ))}
              </ul>
              <Link
                href="/submit"
                className="mt-8 inline-flex items-center gap-2 px-6 py-3.5 rounded-full bg-white text-ink font-semibold hover:bg-ink hover:text-white transition-colors"
              >
                List your car <ArrowUpRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          {/* Community */}
          <div className="lg:col-span-2 relative overflow-hidden rounded-3xl bg-surface border border-line p-8 md:p-12 flex flex-col">
            <p className="text-muted text-sm font-medium">Community</p>
            <h3 className="mt-3 text-3xl md:text-4xl font-semibold tracking-tight leading-[1.1] text-ink">
              8,000+ drivers sharing honest advice.
            </h3>
            <p className="mt-4 text-muted leading-relaxed">
              Ask about import taxes, EVs, or whether that price is fair — people who know Cambodia&apos;s market will answer.
            </p>
            <div className="mt-auto pt-8">
              <Link
                href="/community"
                className="inline-flex items-center gap-2 px-6 py-3.5 rounded-full bg-ink text-white font-semibold hover:bg-brand transition-colors"
              >
                Join the conversation <ArrowUpRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
