import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown, ChevronUp } from 'lucide-react'
import type { ComponentProps } from 'react'

export const Select = SelectPrimitive.Root
export const SelectValue = SelectPrimitive.Value

export function SelectTrigger({
  children,
  className = '',
  ...props
}: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      className={`btn group shrink-0 justify-between gap-2 data-[state=open]:border-line-strong data-[state=open]:bg-paper ${className}`}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown
          size={15}
          aria-hidden="true"
          className="shrink-0 text-muted transition-transform group-data-[state=open]:rotate-180"
        />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )
}

export function SelectContent({
  children,
  className = '',
  ...props
}: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        position="popper"
        sideOffset={6}
        collisionPadding={8}
        className={`z-50 max-h-[var(--radix-select-content-available-height)] min-w-[max(8rem,var(--radix-select-trigger-width))] overflow-hidden rounded-xl border border-line bg-white font-sans text-sm text-ink shadow-lg ${className}`}
        {...props}
      >
        <SelectPrimitive.ScrollUpButton className="flex justify-center py-1 text-muted">
          <ChevronUp size={15} aria-hidden="true" />
        </SelectPrimitive.ScrollUpButton>
        <SelectPrimitive.Viewport className="p-1">
          {children}
        </SelectPrimitive.Viewport>
        <SelectPrimitive.ScrollDownButton className="flex justify-center py-1 text-muted">
          <ChevronDown size={15} aria-hidden="true" />
        </SelectPrimitive.ScrollDownButton>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  )
}

export function SelectItem({
  children,
  className = '',
  ...props
}: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      className={`relative flex min-h-9 cursor-pointer items-center rounded-lg py-2 pr-8 pl-3 outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent data-[highlighted]:text-accent-strong data-[state=checked]:font-medium ${className}`}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="absolute right-2 flex items-center text-accent-strong">
        <Check size={15} aria-hidden="true" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}
