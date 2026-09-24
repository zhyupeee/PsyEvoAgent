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
      { title: 'PsyEvoAgent' },
    ],
    links: [
      { rel: 'stylesheet', href: stylesheet },
      { rel: 'icon', href: '/favicon.ico', sizes: '16x16 32x32 48x48' },
      {
        rel: 'icon',
        href: '/brand/icon-32.png',
        type: 'image/png',
        sizes: '32x32',
      },
      {
        rel: 'apple-touch-icon',
        href: '/brand/icon-180.png',
        sizes: '180x180',
      },
      { rel: 'manifest', href: '/site.webmanifest' },
    ],
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
