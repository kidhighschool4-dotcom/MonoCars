import clsx from 'clsx'

interface LogoProps {
  /** 'dark' = for light backgrounds (black wordmark), 'light' = for dark backgrounds */
  tone?: 'dark' | 'light'
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = {
  sm: { mark: 'w-7 h-7', text: 'text-lg' },
  md: { mark: 'w-8 h-8', text: 'text-xl' },
  lg: { mark: 'w-10 h-10', text: 'text-2xl' },
}

/**
 * FBM mark — an "F" drawn as a car in profile: the stem is the rear, the two arms are roofline and body,
 * and the wheel doubles as the full stop in "FBM.". Built on a 32px grid; reads at 16px.
 */
export function LogoMark({ className, tone = 'brand' }: { className?: string; tone?: 'brand' | 'ink' | 'white' }) {
  const tile = tone === 'brand' ? 'var(--brand)' : tone === 'ink' ? 'var(--ink)' : '#fff'
  const fg = tone === 'white' ? 'var(--ink)' : '#fff'
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="8" fill={tile} />
      {/* stem + roof arm as one stroke so the corner reads as a single bent line */}
      <path d="M10.5 23.5V10.25c0-.97.78-1.75 1.75-1.75H23" fill="none" stroke={fg} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.5 16H18.5" fill="none" stroke={fg} strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="21.75" cy="22" r="2.6" fill={fg} />
    </svg>
  )
}

export default function Logo({ tone = 'dark', size = 'md', className }: LogoProps) {
  const s = sizes[size]
  return (
    <span className={clsx('inline-flex items-center gap-2.5', className)}>
      <LogoMark className={s.mark} />
      <span
        className={clsx(
          'font-bold tracking-tight leading-none',
          s.text,
          tone === 'dark' ? 'text-ink' : 'text-white'
        )}
      >
        FBM<span className="text-brand">.</span>
      </span>
    </span>
  )
}
