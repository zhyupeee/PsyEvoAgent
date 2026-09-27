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
          <span aria-disabled="true" className="text-muted">
            我的记录 · 尚未开放
          </span>
          <Link to="/resources" activeProps={{ 'aria-current': 'page' }}>
            支持资源
          </Link>
          <Link to="/me">我的</Link>
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
