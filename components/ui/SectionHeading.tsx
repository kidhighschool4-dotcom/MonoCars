import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import clsx from 'clsx'

interface SectionHeadingProps {
  eyebrow: string
  title: React.ReactNode
  description?: string
  action?: { href: string; label: string }
  tone?: 'light' | 'dark'
  align?: 'left' | 'center'
}

export default function SectionHeading({
  eyebrow,
  title,
  description,
  action,
  tone = 'light',
  align = 'left',
}: SectionHeadingProps) {
  const dark = tone === 'dark'
  return (
    <div
      className={clsx(
        'flex flex-col gap-6 mb-10 md:mb-12',
        align === 'center' ? 'items-center text-center' : 'md:flex-row md:items-end md:justify-between'
      )}
    >
      <div className={clsx(align === 'center' && 'max-w-2xl')}>
        <p className={clsx('inline-flex items-center gap-2 text-sm font-medium mb-3', dark ? 'text-white/60' : 'text-muted')}>
          <span className="w-1.5 h-1.5 rounded-full bg-brand" />
          {eyebrow}
        </p>
        <h2
          className={clsx(
            'text-3xl md:text-5xl font-semibold tracking-tight leading-[1.08]',
            dark ? 'text-white' : 'text-ink'
          )}
        >
          {title}
        </h2>
        {description && (
          <p className={clsx('mt-4 text-lg leading-relaxed max-w-xl', dark ? 'text-white/60' : 'text-muted', align === 'center' && 'mx-auto')}>
            {description}
          </p>
        )}
      </div>
      {action && (
        <Link
          href={action.href}
          className={clsx(
            'group inline-flex items-center gap-2 self-start md:self-auto px-5 py-3 rounded-full border text-sm font-semibold transition-colors flex-shrink-0',
            dark
              ? 'border-white/20 text-white hover:bg-white hover:text-ink'
              : 'border-line bg-surface text-ink hover:border-ink'
          )}
        >
          {action.label}
          <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      )}
    </div>
  )
}
