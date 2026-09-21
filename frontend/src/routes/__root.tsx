import {
  createRootRoute,
  HeadContent,
  Outlet,
  Scripts,
} from '@tanstack/react-router'
import stylesheet from '../style.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'PsyEvoAgent · 工程检查' },
    ],
    links: [{ rel: 'stylesheet', href: stylesheet }],
  }),
  component: () => (
    <html lang="zh-CN">
      <head>
        <HeadContent />
      </head>
      <body className="min-h-screen bg-paper font-sans text-ink [font-synthesis:none]">
        <Outlet />
        <Scripts />
      </body>
    </html>
  ),
})
