import clsx from 'clsx'
import { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  fullWidth?: boolean
}

export default function Button({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  children,
  className,
  ...props
}: ButtonProps) {
  const base =
    'inline-flex items-center justify-center font-semibold rounded-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed'

  const variants = {
    primary:
      'bg-brand text-white hover:bg-brand-strong focus:ring-brand shadow-sm hover:shadow-md active:scale-[0.98]',
    secondary:
      'border-2 border-brand text-brand bg-transparent hover:bg-brand hover:text-white focus:ring-brand active:scale-[0.98]',
    ghost:
      'text-ink bg-transparent hover:bg-gray-100 focus:ring-gray-300 active:scale-[0.98]',
    danger:
      'bg-brand-deep text-white hover:bg-red-900 focus:ring-brand-deep shadow-sm hover:shadow-md active:scale-[0.98]',
  }

  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-5 py-2.5 text-sm',
    lg: 'px-8 py-3.5 text-base',
  }

  return (
    <button
      className={clsx(base, variants[variant], sizes[size], fullWidth && 'w-full', className)}
      {...props}
    >
      {children}
    </button>
  )
}
