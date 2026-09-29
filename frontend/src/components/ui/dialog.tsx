import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { ComponentProps } from 'react'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close
export const DialogTitle = DialogPrimitive.Title
export const DialogDescription = DialogPrimitive.Description

export function DialogContent({
  className = '',
  ...props
}: ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/40" />
      <DialogPrimitive.Content
        className={`fixed top-1/2 left-1/2 z-50 max-h-[calc(100dvh-32px)] w-full max-w-[min(520px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-line bg-white p-6 text-ink shadow-xl ${className}`}
        {...props}
      />
    </DialogPrimitive.Portal>
  )
}
