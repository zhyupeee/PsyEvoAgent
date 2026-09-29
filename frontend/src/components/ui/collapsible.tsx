import * as CollapsiblePrimitive from '@radix-ui/react-collapsible'
import { ChevronDown } from 'lucide-react'
import type { ComponentProps } from 'react'

export const Collapsible = CollapsiblePrimitive.Root

export function CollapsibleTrigger({
  children,
  className = '',
  ...props
}: ComponentProps<typeof CollapsiblePrimitive.Trigger>) {
  return (
    <CollapsiblePrimitive.Trigger
      className={`group flex min-h-9 w-full cursor-pointer items-center justify-between gap-3 rounded-lg text-left text-sm font-medium text-muted hover:text-ink ${className}`}
      {...props}
    >
      {children}
      <ChevronDown
        size={18}
        aria-hidden="true"
        className="shrink-0 transition-transform group-data-[state=open]:rotate-180"
      />
    </CollapsiblePrimitive.Trigger>
  )
}

export function CollapsibleContent({
  className = '',
  ...props
}: ComponentProps<typeof CollapsiblePrimitive.Content>) {
  return (
    <CollapsiblePrimitive.Content
      className={`data-[state=closed]:hidden ${className}`}
      {...props}
    />
  )
}
