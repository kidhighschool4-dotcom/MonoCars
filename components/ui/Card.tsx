import clsx from 'clsx'
import { HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hover?: boolean
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

export default function Card({
  children,
  hover = true,
  padding = 'md',
  className,
  ...props
}: CardProps) {
  const paddings = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
  }

  return (
    <div
      className={clsx(
        'bg-white rounded-2xl shadow-sm border border-gray-100',
        hover && 'transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5',
        paddings[padding],
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
