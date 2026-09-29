import { Search, Gauge, MessageCircle } from 'lucide-react'
import SectionHeading from '@/components/ui/SectionHeading'

const steps = [
  {
    icon: Search,
    title: 'Search',
    titleKh: 'ស្វែងរក',
    description: 'Filter by budget, body type and province. Every listing shows real photos, mileage and the seller.',
  },
  {
    icon: Gauge,
    title: 'Check the price',
    titleKh: 'ពិនិត្យតម្លៃ',
    description: 'Our AI compares each car with the Cambodian market and tells you if it’s a good deal, fair, or overpriced.',
  },
  {
    icon: MessageCircle,
    title: 'Talk to the seller',
    titleKh: 'ទាក់ទងអ្នកលក់',
    description: 'Message in the app, or call, Telegram or WhatsApp — the way people actually buy cars here.',
  },
]

export default function WhyFBM() {
  return (
    <section className="relative py-20 md:py-28 bg-ink text-white overflow-hidden">
      <div className="absolute inset-0 fbm-grid" aria-hidden="true" />
      <div className="absolute -top-40 right-0 w-[40rem] h-[40rem] rounded-full bg-brand/20 blur-[140px]" aria-hidden="true" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          <div className="lg:col-span-5">
            <SectionHeading
              tone="dark"
              eyebrow="How FBM works"
              title={<>Buy with confidence, <span className="text-brand">not guesswork.</span></>}
              description="Built for how Cambodians actually buy and sell cars."
            />

            {/* Price check preview */}
            <div className="rounded-3xl bg-white/[0.04] border border-white/10 p-6 backdrop-blur">
              <div className="flex items-center justify-between">
                <p className="font-semibold">2020 Toyota Camry</p>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold rounded-full px-2.5 py-1 bg-emerald-400/10 text-emerald-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Good Deal
                </span>
              </div>
              <div className="mt-5 relative h-2 rounded-full bg-gradient-to-r from-emerald-400 via-sky-400 to-rose-400">
                <span className="absolute top-1/2 left-[32%] -translate-x-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-white ring-4 ring-ink" />
              </div>
              <div className="mt-2 flex justify-between text-xs text-white/50">
                <span>Below market</span><span>Fair</span><span>Above market</span>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-2xl bg-white/5 p-4">
                  <p className="text-white/50 text-xs">Asking</p>
                  <p className="text-xl font-semibold tnum mt-1">$18,500</p>
                </div>
                <div className="rounded-2xl bg-white/5 p-4">
                  <p className="text-white/50 text-xs">Market value</p>
                  <p className="text-xl font-semibold tnum mt-1 text-brand">$20,100</p>
                </div>
              </div>
            </div>
          </div>

          <ol className="lg:col-span-7 divide-y divide-white/10 border-y border-white/10">
            {steps.map(({ icon: Icon, title, titleKh, description }, i) => (
              <li key={title} className="group grid grid-cols-[auto_1fr] gap-6 md:gap-10 py-8 md:py-10">
                <span className="text-sm font-medium text-white/40 tnum pt-2">0{i + 1}</span>
                <div>
                  <div className="flex items-center gap-4">
                    <span className="w-12 h-12 rounded-2xl bg-brand/15 text-brand flex items-center justify-center group-hover:bg-brand group-hover:text-white transition-colors">
                      <Icon className="w-6 h-6" />
                    </span>
                    <div>
                      <h3 className="text-2xl md:text-3xl font-semibold tracking-tight">{title}</h3>
                      <p className="text-sm text-white/40" lang="km">{titleKh}</p>
                    </div>
                  </div>
                  <p className="mt-4 text-white/65 text-lg leading-relaxed max-w-lg">{description}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}
