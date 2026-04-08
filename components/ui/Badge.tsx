import clsx from 'clsx'

interface BadgeProps {
  label: 'Good Deal' | 'Fair' | 'Overpriced' | string
  size?: 'sm' | 'md'
  className?: string
}

export default function Badge({ label, size = 'md', className }: BadgeProps) {
  const colorMap: Record<string, string> = {
    'Good Deal': 'bg-emerald-100 text-emerald-800 border border-emerald-200',
    'Fair': 'bg-amber-100 text-amber-800 border border-amber-200',
    'Overpriced': 'bg-red-100 text-red-800 border border-red-200',
  }

  const sizeMap = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
  }

  const color = colorMap[label] || 'bg-gray-100 text-gray-800 border border-gray-200'

  return (
    <span
      className={clsx(
        'inline-flex items-center font-semibold rounded-full',
        color,
        sizeMap[size],
        className
      )}
    >
      {label}
    </span>
  )
}
