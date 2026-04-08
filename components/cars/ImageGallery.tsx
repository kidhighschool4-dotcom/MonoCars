'use client'

import { useState } from 'react'

interface ImageGalleryProps {
  images: string[]
  alt: string
}

export default function ImageGallery({ images, alt }: ImageGalleryProps) {
  const [activeIdx, setActiveIdx] = useState(0)

  return (
    <div className="bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100">
      {/* Main image */}
      <div className="aspect-video overflow-hidden bg-gray-100">
        <img
          src={images[activeIdx]}
          alt={alt}
          className="w-full h-full object-cover transition-all duration-300"
        />
      </div>
      {/* Thumbnails */}
      {images.length > 1 && (
        <div className="grid grid-cols-4 gap-2 p-3">
          {images.map((img, idx) => (
            <button
              key={idx}
              onClick={() => setActiveIdx(idx)}
              className={`aspect-video rounded-xl overflow-hidden border-2 transition-all ${
                activeIdx === idx
                  ? 'border-[#CBA135] shadow-md'
                  : 'border-transparent hover:border-[#CBA135]/50'
              }`}
            >
              <img
                src={img}
                alt={`View ${idx + 1}`}
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
