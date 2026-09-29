'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import SafeImage from '@/components/ui/SafeImage'

interface ImageGalleryProps {
  images: string[]
  alt: string
}

export default function ImageGallery({ images, alt }: ImageGalleryProps) {
  const [activeIdx, setActiveIdx] = useState(0)
  const many = images.length > 1
  const go = (dir: 1 | -1) => setActiveIdx((i) => (i + dir + images.length) % images.length)

  return (
    <div>
      <div className="relative aspect-[16/10] rounded-3xl overflow-hidden bg-paper">
        <SafeImage src={images[activeIdx]} alt={alt} className="w-full h-full object-cover" />
        {many && (
          <>
            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Previous photo"
              className="absolute left-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/90 backdrop-blur text-ink flex items-center justify-center hover:bg-white shadow-md"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Next photo"
              className="absolute right-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/90 backdrop-blur text-ink flex items-center justify-center hover:bg-white shadow-md"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
            <span className="absolute bottom-4 right-4 rounded-full bg-ink/70 text-white text-xs font-medium px-3 py-1.5 tnum">
              {activeIdx + 1} / {images.length}
            </span>
          </>
        )}
      </div>

      {many && (
        <div className="mt-3 grid grid-cols-4 sm:grid-cols-6 gap-2">
          {images.map((img, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setActiveIdx(idx)}
              aria-label={`Show photo ${idx + 1}`}
              aria-current={activeIdx === idx}
              className={clsx(
                'aspect-[4/3] rounded-xl overflow-hidden ring-2 ring-offset-2 ring-offset-paper transition-all',
                activeIdx === idx ? 'ring-brand' : 'ring-transparent opacity-70 hover:opacity-100'
              )}
            >
              <SafeImage src={img} alt="" className="w-full h-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
