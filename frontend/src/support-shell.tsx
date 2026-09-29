import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query'
import { Link, useLocation, useNavigate } from '@tanstack/react-router'
import { HeartHandshake, MessageSquare, Settings } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { getIdentity, identitySchema } from './account-api'
import { z } from 'zod'
import { Brand } from './brand'
import { preferencesQuery } from './support-api'
import { privateChangeOrigin, privateChangeSchema } from './history-page'

export function SupportPage({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      }),
  )
  return (
    <QueryClientProvider client={client}>
      <Shell>{children}</Shell>
    </QueryClientProvider>
  )
}

function Shell({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
    refetchInterval: 30000,
  })
  useEffect(() => {
    const channel = new BroadcastChannel('psyevo-private-change')
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const change = privateChangeSchema.safeParse(event.data)
      if (!change.success || change.data.origin === privateChangeOrigin) return
      if (change.data.type !== 'session-updated') window.location.reload()
    }
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) window.location.reload()
    }
    window.addEventListener('pageshow', restore)
    return () => {
      channel.close()
      window.removeEventListener('pageshow', restore)
    }
  }, [])
  useEffect(() => {
    if (identity.data === null) void navigate({ to: '/login', replace: true })
  }, [identity.data, navigate])
  if (identity.isPending || (!identity.isError && identity.data === null))
    return (
      <SupportLayout busy>
        <p role="status" className="sr-only">
          正在确认登录状态…
        </p>
      </SupportLayout>
    )
  if (identity.isError)
    return (
      <>
        <p role="alert">无法确认登录状态，内容已隐藏。</p>
        <button className="btn" onClick={() => void identity.refetch()}>
          重试
        </button>
      </>
    )
  return identity.data ? (
    <OwnerScope key={identity.data.user_id} identity={identity.data}>
      {children}
    </OwnerScope>
  ) : null
}

function OwnerScope({
  identity,
  children,
}: {
  identity: z.infer<typeof identitySchema>
  children: ReactNode
}) {
  const [client] = useState(() => {
    const value = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    value.setQueryData(['identity'], identity)
    return value
  })
  useEffect(() => {
    client.setQueryData(['identity'], identity)
    return () => {
      client.clear()
    }
  }, [client, identity])
  useEffect(() => {
    const channel = new BroadcastChannel('psyevo-private-change')
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const change = privateChangeSchema.safeParse(event.data)
      if (!change.success || change.data.origin === privateChangeOrigin) return
      if (change.data.type !== 'session-updated') return
      const { sessionId } = change.data
      void client.invalidateQueries({
        predicate: ({ queryKey }) =>
          queryKey[0] === 'sessions' ||
          (['session', 'current-run', 'history', 'timeline'].includes(
            String(queryKey[0]),
          ) &&
            queryKey[1] === sessionId),
      })
    }
    return () => channel.close()
  }, [client])
  return (
    <QueryClientProvider client={client}>
      <Layout>{children}</Layout>
    </QueryClientProvider>
  )
}

const navLinkClass =
  'inline-flex min-h-10 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-ink no-underline transition-colors hover:bg-ink/5 aria-[current=page]:bg-accent aria-[current=page]:text-accent-strong'

function Layout({ children }: { children: ReactNode }) {
  const preferences = useQuery(preferencesQuery)
  return (
    <SupportLayout
      large={preferences.data?.display_preferences.font_size === 'large'}
      reduced={preferences.data?.display_preferences.reduced_motion !== false}
    >
      {children}
    </SupportLayout>
  )
}

function SupportLayout({
  children,
  large = false,
  reduced = true,
  busy = false,
}: {
  children: ReactNode
  large?: boolean
  reduced?: boolean
  busy?: boolean
}) {
  const pathname = useLocation({ select: (s) => s.pathname })
  const chatMode = pathname.startsWith('/chat')
  return (
    <div
      className="support-shell flex h-dvh flex-col overflow-hidden bg-paper text-ink"
      data-large={large}
      data-reduced={reduced}
    >
      <a href="#support-main" className="skip-link">
        跳到主要内容
      </a>
      <aside className="support-nav grid shrink-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b border-line bg-white px-4 py-2 page:grid-cols-[auto_minmax(0,1fr)_auto]">
        <Brand />
        <nav
          aria-label="主要导航"
          className="col-span-2 row-start-2 flex items-center gap-1 page:col-span-1 page:col-start-2 page:row-start-1"
        >
          <Link
            to="/chat"
            className={navLinkClass}
            activeProps={{ 'aria-current': 'page' }}
          >
            <MessageSquare size={18} aria-hidden="true" />
            对话
          </Link>
          <Link
            to="/resources"
            activeOptions={{ includeSearch: false }}
            className={navLinkClass}
            activeProps={{ 'aria-current': 'page' }}
          >
            <HeartHandshake size={18} aria-hidden="true" />
            支持资源
          </Link>
        </nav>
        <nav
          aria-label="个人设置"
          className="col-start-2 row-start-1 justify-self-end page:col-start-3"
        >
          <Link
            to="/me"
            search={{ section: 'preferences' }}
            activeOptions={{ includeSearch: false }}
            className={navLinkClass}
            activeProps={{ 'aria-current': 'page' }}
          >
            <Settings size={18} aria-hidden="true" />
            设置
          </Link>
        </nav>
      </aside>
      <main
        id="support-main"
        aria-busy={busy}
        className={`support-main min-w-0 bg-white ${
          chatMode
            ? 'flex min-h-0 flex-1 flex-col'
            : 'min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-8 [scrollbar-gutter:stable] page:px-10'
        }`}
      >
        {children}
      </main>
    </div>
  )
}
