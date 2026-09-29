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

/** FBM mark: a blue tile with three speed lines stepping forward. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="9" fill="var(--brand)" />
      <rect x="8" y="9" width="16" height="3.2" rx="1.6" fill="#fff" />
      <rect x="8" y="14.4" width="11" height="3.2" rx="1.6" fill="#fff" />
      <rect x="8" y="19.8" width="6" height="3.2" rx="1.6" fill="#fff" opacity="0.75" />
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
