import type { ComponentProps } from 'react'

export function Input({ className = '', ...props }: ComponentProps<'input'>) {
  return <input className={`field w-full ${className}`} {...props} />
}
