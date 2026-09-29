import clsx from 'clsx'

interface BadgeProps {
  label: 'Good Deal' | 'Fair' | 'Overpriced' | string
  size?: 'sm' | 'md'
  className?: string
}

const colorMap: Record<string, { chip: string; dot: string }> = {
  'Good Deal':  { chip: 'bg-emerald-50 text-emerald-700 ring-emerald-600/15', dot: 'bg-emerald-500' },
  'Fair':       { chip: 'bg-sky-50 text-sky-700 ring-sky-600/15',             dot: 'bg-sky-500' },
  'Overpriced': { chip: 'bg-rose-50 text-rose-700 ring-rose-600/15',          dot: 'bg-rose-500' },
}

const displayLabel: Record<string, string> = {
  'Fair': 'Fair price',
}

export default function Badge({ label, size = 'md', className }: BadgeProps) {
  const color = colorMap[label] ?? { chip: 'bg-paper text-muted ring-line', dot: 'bg-subtle' }

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 font-semibold rounded-full ring-1 ring-inset whitespace-nowrap',
        color.chip,
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1 text-sm',
        className
      )}
    >
      <span className={clsx('w-1.5 h-1.5 rounded-full', color.dot)} />
      {displayLabel[label] ?? label}
    </span>
  )
}
