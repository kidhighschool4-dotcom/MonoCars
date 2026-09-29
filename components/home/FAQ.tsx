import { Plus } from 'lucide-react'
import SectionHeading from '@/components/ui/SectionHeading'

const faqs = [
  {
    q: 'How does the AI price check work?',
    a: 'We compare the car’s make, model, year and mileage against similar cars in Cambodia and show whether the asking price is below market, fair, or above market. Use it as a guide when you negotiate.',
  },
  {
    q: 'Is it free to list my car?',
    a: 'Yes. Create an account, add photos and details, and your listing goes live with a price estimate straight away.',
  },
  {
    q: 'How do I contact a seller?',
    a: 'Open any listing to message the seller in the app, or call them, or reach them on Telegram or WhatsApp.',
  },
  {
    q: 'Are the prices in USD or Riel?',
    a: 'Prices are listed in US dollars, with an approximate Riel amount shown underneath for reference.',
  },
  {
    q: 'What is the AI Advisor?',
    a: 'Tell it your budget and how you’ll use the car, and it suggests matching listings and explains why they fit.',
  },
]

export default function FAQ() {
  return (
    <section className="py-20 md:py-28 bg-surface border-t border-line">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-12 gap-10">
        <div className="lg:col-span-4">
          <SectionHeading eyebrow="FAQ" title="Questions, answered." />
        </div>
        <div className="lg:col-span-8 divide-y divide-line border-y border-line">
          {faqs.map((f) => (
            <details key={f.q} className="group py-6">
              <summary className="flex items-center justify-between gap-6 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                <span className="text-lg md:text-xl font-semibold text-ink">{f.q}</span>
                <span className="w-10 h-10 rounded-full border border-line flex items-center justify-center flex-shrink-0 group-open:bg-ink group-open:border-ink group-open:text-white transition-colors">
                  <Plus className="w-5 h-5 group-open:rotate-45 transition-transform" />
                </span>
              </summary>
              <p className="mt-4 text-muted text-[17px] leading-relaxed max-w-2xl">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
