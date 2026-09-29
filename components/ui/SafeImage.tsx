'use client'

import { useState } from 'react'
import { Car } from 'lucide-react'
import clsx from 'clsx'

type SafeImageProps = React.ImgHTMLAttributes<HTMLImageElement> & { src: string }

/** <img> that swaps to a neutral FBM placeholder when the URL is dead (e.g. removed Unsplash photos). */
export default function SafeImage({ src, alt, className, ...props }: SafeImageProps) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)

  if (!src || failedSrc === src) {
    return (
      <div
        role="img"
        aria-label={alt || 'Photo unavailable'}
        className={clsx('flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-paper to-brand-soft text-subtle', className)}
      >
        <Car className="w-10 h-10" strokeWidth={1.5} />
        <span className="text-xs font-medium">Photo coming soon</span>
      </div>
    )
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={className} onError={() => setFailedSrc(src)} {...props} />
}
