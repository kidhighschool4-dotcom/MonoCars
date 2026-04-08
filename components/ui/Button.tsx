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
      'bg-[#CBA135] text-[#1A1A1A] hover:bg-[#b8922e] focus:ring-[#CBA135] shadow-sm hover:shadow-md active:scale-[0.98]',
    secondary:
      'border-2 border-[#CBA135] text-[#CBA135] bg-transparent hover:bg-[#CBA135] hover:text-[#1A1A1A] focus:ring-[#CBA135] active:scale-[0.98]',
    ghost:
      'text-[#1A1A1A] bg-transparent hover:bg-gray-100 focus:ring-gray-300 active:scale-[0.98]',
    danger:
      'bg-[#7A1E1E] text-white hover:bg-red-900 focus:ring-[#7A1E1E] shadow-sm hover:shadow-md active:scale-[0.98]',
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
