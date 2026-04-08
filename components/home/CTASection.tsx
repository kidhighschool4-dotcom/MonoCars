import Link from 'next/link'
import { PlusCircle, Users } from 'lucide-react'

export default function CTASection() {
  return (
    <section className="py-16 md:py-20 bg-[#F8F5F0]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Sell CTA */}
          <div className="relative overflow-hidden bg-[#1A1A1A] rounded-3xl p-8 md:p-10">
            <div className="absolute top-0 right-0 w-48 h-48 rounded-full bg-[#CBA135]/10 -translate-y-12 translate-x-12" />
            <div className="absolute bottom-0 left-0 w-32 h-32 rounded-full bg-[#7A1E1E]/20 translate-y-10 -translate-x-10" />
            <div className="relative">
              <div className="w-12 h-12 rounded-2xl bg-[#CBA135]/10 flex items-center justify-center mb-5">
                <PlusCircle className="w-6 h-6 text-[#CBA135]" />
              </div>
              <h3 className="text-2xl md:text-3xl font-black text-white mb-3">
                Have a car to sell?
              </h3>
              <p className="text-gray-400 text-sm leading-relaxed mb-6 max-w-xs">
                List your car for free and reach thousands of verified buyers across Cambodia.
                Get smart pricing insights instantly.
              </p>
              <Link
                href="/submit"
                className="inline-flex items-center gap-2 px-6 py-3 bg-[#CBA135] text-[#1A1A1A] font-bold rounded-xl hover:bg-[#b8922e] transition-all duration-200 text-sm"
              >
                <PlusCircle className="w-4 h-4" />
                Submit a Listing
              </Link>
            </div>
          </div>

          {/* Community CTA */}
          <div className="relative overflow-hidden bg-gradient-to-br from-[#7A1E1E] to-[#5a1616] rounded-3xl p-8 md:p-10">
            <div className="absolute top-0 right-0 w-48 h-48 rounded-full bg-white/5 -translate-y-12 translate-x-12" />
            <div className="absolute bottom-0 left-0 w-32 h-32 rounded-full bg-[#CBA135]/10 translate-y-10 -translate-x-10" />
            <div className="relative">
              <div className="w-12 h-12 rounded-2xl bg-white/10 flex items-center justify-center mb-5">
                <Users className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-2xl md:text-3xl font-black text-white mb-3">
                Join the community
              </h3>
              <p className="text-red-200 text-sm leading-relaxed mb-6 max-w-xs">
                Connect with 8,000+ car enthusiasts in Cambodia. Share reviews, get advice,
                and discover great deals together.
              </p>
              <Link
                href="/community"
                className="inline-flex items-center gap-2 px-6 py-3 bg-white text-[#7A1E1E] font-bold rounded-xl hover:bg-gray-100 transition-all duration-200 text-sm"
              >
                <Users className="w-4 h-4" />
                Explore Community
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
