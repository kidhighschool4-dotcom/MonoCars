import Hero from '@/components/home/Hero'
import FeaturedCars from '@/components/home/FeaturedCars'
import FeaturedEvents from '@/components/home/FeaturedEvents'
import CTASection from '@/components/home/CTASection'
import WhyMonoCars from '@/components/home/WhyMonoCars'

export default function HomePage() {
  return (
    <>
      <Hero />
      <FeaturedCars />
      <WhyMonoCars />
      <FeaturedEvents />
      <CTASection />
    </>
  )
}
