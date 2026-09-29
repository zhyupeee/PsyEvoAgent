import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
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
  if (identity.isPending) return <p role="status">正在确认登录状态…</p>
  if (identity.isError)
    return (
      <>
        <p role="alert">无法确认登录状态，内容已隐藏。</p>
        <button onClick={() => void identity.refetch()}>重试</button>
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

function Layout({ children }: { children: ReactNode }) {
  const preferences = useQuery(preferencesQuery)
  return (
    <div
      className="support-shell"
      data-large={preferences.data?.display_preferences.font_size === 'large'}
      data-reduced={
        preferences.data?.display_preferences.reduced_motion !== false
      }
    >
      <a href="#support-main" className="skip-link">
        跳到主要内容
      </a>
      <aside className="support-nav">
        <Brand />
        <nav aria-label="主要导航">
          <Link to="/chat" activeProps={{ 'aria-current': 'page' }}>
            对话
          </Link>
          <Link
            to="/resources"
            activeOptions={{ includeSearch: false }}
            activeProps={{ 'aria-current': 'page' }}
          >
            支持资源
          </Link>
        </nav>
        <nav aria-label="个人设置" className="settings-nav">
          <Link
            to="/me"
            search={{ section: 'preferences' }}
            activeOptions={{ includeSearch: false }}
            activeProps={{ 'aria-current': 'page' }}
          >
            设置
          </Link>
        </nav>
        <p className="text-sm text-muted">
          按自己的节奏。
          <br />
          随时可以停下。
        </p>
      </aside>
      <main id="support-main" className="support-main">
        {children}
      </main>
    </div>
  )
}
