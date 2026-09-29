import type { ComponentProps } from 'react'

export function Textarea({
  className = '',
  ...props
}: ComponentProps<'textarea'>) {
  return <textarea className={`field resize-y ${className}`} {...props} />
}
