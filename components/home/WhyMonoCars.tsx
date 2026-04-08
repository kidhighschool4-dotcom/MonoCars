import { ShieldCheck, TrendingUp, Users } from 'lucide-react'

const reasons = [
  {
    icon: TrendingUp,
    title: 'Smart Pricing',
    titleKh: 'តម្លៃឆ្លាតវៃ',
    description: 'AI-powered market analysis shows you if a car is a good deal, fairly priced, or overpriced before you decide.',
  },
  {
    icon: ShieldCheck,
    title: 'Trusted Listings',
    titleKh: 'បញ្ជីទុកចិត្ត',
    description: 'Every listing is reviewed for accuracy. We surface red flags so you can buy with confidence across Cambodia.',
  },
  {
    icon: Users,
    title: 'Cambodia Community',
    titleKh: 'សហគមន៍ខ្មែរ',
    description: 'Connect with 8,000+ local car enthusiasts. Get honest advice from people who know Cambodia\'s car market.',
  },
]

export default function WhyMonoCars() {
  return (
    <section className="py-16 md:py-20 bg-[#1A1A1A]">
      {/* Gold top border */}
      <div className="h-px bg-gradient-to-r from-transparent via-[#CBA135] to-transparent mb-0" />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <p className="text-[#CBA135] text-sm font-semibold uppercase tracking-wider mb-2">
            Why MonoCars
          </p>
          <h2 className="text-3xl md:text-4xl font-black text-white">
            Built for Cambodia
          </h2>
          <p className="text-gray-400 mt-3 text-sm max-w-xl mx-auto">
            Not a copy-paste from somewhere else. Built from the ground up for how Cambodians actually buy and sell cars.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {reasons.map(({ icon: Icon, title, titleKh, description }) => (
            <div key={title} className="text-center">
              <div className="w-14 h-14 rounded-2xl bg-[#CBA135]/10 border border-[#CBA135]/20 flex items-center justify-center mx-auto mb-5">
                <Icon className="w-7 h-7 text-[#CBA135]" />
              </div>
              <h3 className="text-xl font-bold text-white mb-1">{title}</h3>
              <p className="text-xs text-[#CBA135]/60 mb-3" lang="km">{titleKh}</p>
              <p className="text-gray-400 text-sm leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
