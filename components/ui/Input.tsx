import clsx from 'clsx'
import { InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
}

export default function Input({ label, error, helperText, className, id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-sm font-medium text-ink"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={clsx(
          'w-full px-4 py-2.5 rounded-xl border text-ink bg-white text-sm transition-all duration-200',
          'focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
          'placeholder:text-gray-400',
          error
            ? 'border-red-400 focus:ring-red-400 focus:border-red-400'
            : 'border-line hover:border-gray-300',
          className
        )}
        {...props}
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
      {helperText && !error && <p className="text-xs text-muted">{helperText}</p>}
    </div>
  )
}
