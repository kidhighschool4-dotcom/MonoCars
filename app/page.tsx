import Hero from '@/components/home/Hero'
import BrandStrip from '@/components/home/BrandStrip'
import FeaturedCars from '@/components/home/FeaturedCars'
import BrowseByType from '@/components/home/BrowseByType'
import WhyFBM from '@/components/home/WhyFBM'
import FeaturedEvents from '@/components/home/FeaturedEvents'
import CTASection from '@/components/home/CTASection'
import FAQ from '@/components/home/FAQ'

export default function HomePage() {
  return (
    <>
      <Hero />
      <BrandStrip />
      <FeaturedCars />
      <BrowseByType />
      <WhyFBM />
      <FeaturedEvents />
      <CTASection />
      <FAQ />
    </>
  )
}
