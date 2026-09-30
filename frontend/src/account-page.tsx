import { useForm } from '@tanstack/react-form'
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
} from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  Database,
  Eye,
  EyeOff,
  KeyRound,
  LockKeyhole,
  Mail,
  User,
} from 'lucide-react'
import { DeletionReceipts, notifyPrivateChange } from './history-page'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import {
  getIdentity,
  identitySchema,
  request,
  RequestError,
} from './account-api'
import { Brand } from './brand'
import { Preferences } from './preferences'
import { ModelSettings } from './model-settings'

const control = 'field'
const button = 'btn btn-primary'
const tabLinkClass =
  '-mb-px inline-flex min-h-11 items-center border-b-2 border-transparent px-1 text-sm font-medium text-muted no-underline transition-colors hover:text-ink aria-[current=page]:border-status aria-[current=page]:text-ink'
const settingsCardClass =
  'settings-card mb-6 grid gap-4 rounded-xl border border-line bg-white p-4 page:p-6'
type Page = 'login' | 'register'
type FormMode = 'login' | 'register' | 'reset' | 'change'

export function AccountPage({ page }: { page: Page }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: 0 },
          mutations: { retry: false },
        },
      }),
  )
  return (
    <QueryClientProvider client={client}>
      <Account page={page} />
    </QueryClientProvider>
  )
}

function ErrorNotice({ error }: { error: Error | null }) {
  const ref = useRef<HTMLParagraphElement>(null)
  useEffect(() => {
    if (error) ref.current?.focus()
  }, [error])
  return error ? (
    <p
      role="alert"
      tabIndex={-1}
      ref={ref}
      className="my-4 rounded-lg border border-danger/20 bg-danger/5 p-3 text-sm text-danger"
    >
      {error instanceof RequestError
        ? error.message
        : error.message || '请求未完成，请稍后重试。'}
    </p>
  ) : null
}

function Account({ page }: { page: Page }) {
  const navigate = useNavigate()
  const [reset, setReset] = useState(false)
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
    refetchInterval: 60_000,
  })
  useEffect(() => {
    if (identity.data) void navigate({ to: '/chat', replace: true })
  }, [identity.data, navigate])
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
          <Brand />
          <nav
            aria-label="账号导航"
            className="flex items-center gap-5 text-sm"
          >
            {identity.data ? (
              <Link
                to="/me"
                search={{ section: 'security' }}
                className="text-status"
              >
                我的账号
              </Link>
            ) : (
              <>
                <Link to="/login" className="text-status">
                  登录
                </Link>
                <Link to="/register" className="text-status">
                  注册
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto min-h-[70vh] max-w-4xl px-5 py-10 sm:px-8 sm:py-16">
        <ErrorNotice error={identity.error} />
        {identity.isError ? (
          <button
            className={button}
            onClick={() => void identity.refetch()}
            disabled={identity.isFetching}
          >
            {identity.isFetching ? '正在重试…' : '重试'}
          </button>
        ) : null}
        {identity.isPending ? (
          <p role="status" className="sr-only">
            正在确认登录状态…
          </p>
        ) : null}
        {identity.data === null ? (
          <section className="mx-auto max-w-lg rounded-lg border border-line bg-white p-6 sm:p-9">
            <h1 className="mb-3 text-2xl font-semibold">
              {page === 'register'
                ? '创建账号'
                : reset
                  ? '找回密码'
                  : '登录 PsyEvoAgent'}
            </h1>
            <p className="mb-7 text-sm leading-6 text-muted">
              {page === 'register'
                ? '验证邮箱后，即可创建你的账号。'
                : reset
                  ? '通过邮箱验证码设置新密码。'
                  : '使用邮箱和密码登录。'}
            </p>
            <IdentityForm
              key={`${page}-${reset}`}
              mode={
                page === 'register' ? 'register' : reset ? 'reset' : 'login'
              }
            />
            {page === 'login' ? (
              <button
                className="btn-ghost mt-3 -ml-2.5 text-sm"
                onClick={() => setReset(!reset)}
              >
                {reset ? '返回登录' : '忘记密码？'}
              </button>
            ) : null}
            <p className="mt-6 border-t border-line pt-5 text-sm text-muted">
              <Link
                className="link-inline"
                to={page === 'register' ? '/login' : '/register'}
              >
                {page === 'register' ? '已有账号？登录' : '没有账号？注册'}
              </Link>
            </p>
          </section>
        ) : null}
      </main>
      <footer className="mx-auto max-w-6xl border-t border-line px-5 py-6 text-sm leading-7 text-muted sm:px-8">
        PsyEvoAgent · 按自己的节奏，随时可以停下。
      </footer>
    </div>
  )
}

export function SettingsPage({
  section,
}: {
  section: 'preferences' | 'models' | 'security' | 'data'
}) {
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
  const logout = useMutation({
    mutationFn: async () => {
      if (!identity.data) return
      try {
        await request('/auth/logout', z.null(), {
          method: 'POST',
          csrf: identity.data.csrf_token,
        })
      } catch (error) {
        if (!(error instanceof RequestError && error.status === 401))
          throw error
      }
      notifyPrivateChange({ type: 'signed-out' })
      window.location.replace('/login')
    },
  })
  if (!identity.data) return null
  return (
    <div className="support-content settings-page mx-auto w-full max-w-[840px] pt-6 pb-12 page:pt-8">
      <header className="support-header mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">设置</h1>
        <Link to="/me/support-card" className="btn mt-3">
          支持备忘卡
        </Link>
      </header>
      <nav
        className="resource-tabs mb-6 flex flex-wrap gap-x-6 gap-y-1 border-b border-line"
        aria-label="设置分类"
      >
        <Link
          to="/me"
          search={{ section: 'models' }}
          className={tabLinkClass}
          aria-current={section === 'models' ? 'page' : undefined}
        >
          模型配置
        </Link>
        <Link
          to="/me"
          search={{ section: 'preferences' }}
          className={tabLinkClass}
          aria-current={section === 'preferences' ? 'page' : undefined}
        >
          交流与显示
        </Link>
        <Link
          to="/me"
          search={{ section: 'security' }}
          className={tabLinkClass}
          aria-current={section === 'security' ? 'page' : undefined}
        >
          账号安全
        </Link>
        <Link
          to="/me"
          search={{ section: 'data' }}
          className={tabLinkClass}
          aria-current={section === 'data' ? 'page' : undefined}
        >
          数据管理
        </Link>
      </nav>
      <ErrorNotice error={logout.error} />
      {section === 'models' ? (
        <ModelSettings csrf={identity.data.csrf_token} />
      ) : null}
      <div hidden={section !== 'preferences'}>
        <Preferences csrf={identity.data.csrf_token} />
      </div>
      <div hidden={section !== 'security'}>
        <section className={settingsCardClass}>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <User size={20} aria-hidden="true" className="text-status" />
            我的账号
          </h2>
          <p className="break-all text-sm text-muted">
            当前账号：{identity.data.email}
          </p>
          <button
            className="btn justify-self-start"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            退出账号
          </button>
        </section>
        <section className={settingsCardClass}>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <KeyRound size={20} aria-hidden="true" className="text-status" />
            修改密码
          </h2>
          <p className="text-sm text-muted">
            修改后所有已登录设备将退出，请使用新密码重新登录。
          </p>
          <IdentityForm mode="change" csrf={identity.data.csrf_token} />
        </section>
      </div>
      <div hidden={section !== 'data'}>
        <section className={settingsCardClass}>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <Database size={20} aria-hidden="true" className="text-status" />
            对话与数据
          </h2>
          <p className="text-sm text-muted">
            在对话列表中查找会话，进入后可以归档、恢复或确认删除。
          </p>
          <Link to="/chat" className="link-inline justify-self-start text-sm">
            管理和删除会话 →
          </Link>
        </section>
        <DeletionReceipts csrf={identity.data.csrf_token} />
      </div>
    </div>
  )
}

function IdentityForm({ mode, csrf }: { mode: FormMode; csrf?: string }) {
  const isCode = mode === 'register' || mode === 'reset'
  const isNew = mode !== 'login'
  const [codeEmail, setCodeEmail] = useState('')
  const currentCodeEmail = useRef('')
  const [sendStates, setSendStates] = useState<
    Record<string, { pending?: boolean; sent?: boolean; waitUntil?: number }>
  >({})
  const currentSend = sendStates[codeEmail]
  const waitUntil = currentSend?.waitUntil ?? 0
  const sentTo = currentSend?.sent ? codeEmail : ''
  const sending = currentSend?.pending ?? false
  const [remaining, setRemaining] = useState(0)
  const [error, setError] = useState<Error | null>(null)
  const [success, setSuccess] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  useEffect(() => {
    const tick = () =>
      setRemaining(Math.max(0, Math.ceil((waitUntil - Date.now()) / 1000)))
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [waitUntil])
  const submit = useMutation({
    mutationFn: async (value: {
      email: string
      code: string
      password: string
      current: string
      repeat: string
    }) => {
      setError(null)
      const email = value.email.trim().toLowerCase()
      if (
        mode !== 'change' &&
        !z.string().email().max(254).safeParse(email).success
      )
        throw new Error('请输入有效的邮箱地址。')
      if (isCode && !/^\d{6}$/.test(value.code))
        throw new Error('请输入 6 位邮箱验证码。')
      if (isNew && value.password !== value.repeat)
        throw new Error('两次输入的新密码不一致。')
      if (
        !z
          .string()
          .min(isNew ? 6 : 1)
          .max(128)
          .safeParse(value.password).success
      )
        throw new Error('新密码需为 6～128 位。')
      if (mode === 'login' || mode === 'register') {
        await request(`/auth/${mode}`, identitySchema, {
          method: 'POST',
          body: {
            email,
            password: value.password,
            ...(mode === 'register' ? { code: value.code } : {}),
          },
        })
        window.location.replace('/chat')
      } else {
        await request(
          mode === 'reset' ? '/auth/password-reset' : '/auth/password-change',
          z.null(),
          {
            method: 'POST',
            csrf,
            body:
              mode === 'reset'
                ? { email, code: value.code, new_password: value.password }
                : {
                    current_password: value.current,
                    new_password: value.password,
                  },
          },
        )
        if (mode === 'change') window.location.replace('/login')
        else setSuccess(true)
      }
    },
    onError: (failure) => setError(failure),
  })
  const form = useForm({
    defaultValues: {
      email: '',
      code: '',
      password: '',
      current: '',
      repeat: '',
    },
    onSubmit: async ({ value }) => {
      await submit.mutateAsync(value).catch(() => undefined)
    },
  })
  const send = useMutation({
    mutationFn: async (email: string) => {
      if (!z.string().email().max(254).safeParse(email).success)
        throw new Error('请输入有效的邮箱地址。')
      await request(
        mode === 'register'
          ? '/auth/registration-codes'
          : '/auth/password-reset-codes',
        z.object({ message: z.string() }),
        { method: 'POST', body: { email } },
      )
    },
    onMutate: (email) => {
      if (currentCodeEmail.current === email) setError(null)
      setSendStates((states) => ({
        ...states,
        [email]: { ...states[email], pending: true },
      }))
    },
    onSuccess: (_, email) => {
      setSendStates((states) => ({
        ...states,
        [email]: {
          ...states[email],
          sent: true,
          waitUntil: Date.now() + 60_000,
        },
      }))
    },
    onError: (failure, email) => {
      if (currentCodeEmail.current === email) setError(failure)
      if (failure instanceof RequestError && failure.status === 429)
        setSendStates((states) => ({
          ...states,
          [email]: { ...states[email], waitUntil: Date.now() + 60_000 },
        }))
    },
    onSettled: (_, __, email) => {
      setSendStates((states) => ({
        ...states,
        [email]: { ...states[email], pending: false },
      }))
    },
  })
  if (success)
    return (
      <div role="status" className="space-y-4 leading-7">
        <p>密码重置请求已完成。如邮箱关联有效账号，请使用新密码重新登录。</p>
        <a href="/login" className="link-inline">
          返回登录
        </a>
      </div>
    )
  return (
    <form
      className="grid gap-5"
      onSubmit={(event) => {
        event.preventDefault()
        void form.handleSubmit()
      }}
    >
      {mode !== 'change' ? (
        <form.Field name="email">
          {(field) => (
            <label className="grid gap-2 text-sm font-medium">
              邮箱
              <span className="relative block">
                <Mail
                  size={16}
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
                />
                <input
                  className={`${control} pl-9`}
                  type="email"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  maxLength={254}
                  value={field.state.value}
                  onChange={(event) => {
                    field.handleChange(event.target.value)
                    const email = event.target.value.trim().toLowerCase()
                    currentCodeEmail.current = email
                    setCodeEmail(email)
                    form.setFieldValue('code', '')
                    setError(null)
                  }}
                />
              </span>
            </label>
          )}
        </form.Field>
      ) : null}
      {isCode ? (
        <div>
          <form.Field name="code">
            {(field) => (
              <div className="grid gap-2 text-sm font-medium">
                <label htmlFor={`${mode}-code`}>邮箱验证码</label>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="relative block min-w-0 flex-1">
                    <KeyRound
                      size={16}
                      aria-hidden="true"
                      className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
                    />
                    <input
                      className={`${control} min-w-0 pl-9`}
                      inputMode="numeric"
                      id={`${mode}-code`}
                      autoComplete="one-time-code"
                      pattern="[0-9]{6}"
                      required
                      maxLength={6}
                      value={field.state.value}
                      onChange={(event) =>
                        field.handleChange(event.target.value)
                      }
                    />
                  </span>
                  <button
                    type="button"
                    className="btn px-4 text-accent-strong"
                    onClick={() => {
                      form.setFieldValue('code', '')
                      send.mutate(codeEmail)
                    }}
                    disabled={sending || remaining > 0}
                  >
                    {sending
                      ? '正在发送…'
                      : remaining
                        ? `${remaining}秒后重发`
                        : '发送验证码'}
                  </button>
                </div>
              </div>
            )}
          </form.Field>
          <p className="mt-2 text-xs leading-5 text-muted" role="status">
            {sentTo
              ? `验证码已发送至 ${sentTo}，10分钟内有效。`
              : '验证码用于确认邮箱控制权。'}
          </p>
        </div>
      ) : null}
      {mode === 'change' ? (
        <form.Field name="current">
          {(field) => (
            <label className="grid gap-2 text-sm font-medium">
              当前密码
              <span className="relative block">
                <LockKeyhole
                  size={16}
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
                />
                <input
                  className={`${control} pl-9`}
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={128}
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
              </span>
            </label>
          )}
        </form.Field>
      ) : null}
      <form.Field name="password">
        {(field) => (
          <label className="grid gap-2 text-sm font-medium">
            {mode === 'reset' || mode === 'change' ? '新密码' : '密码'}
            <span className="relative block">
              <LockKeyhole
                size={16}
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
              />
              <input
                className={`${control} pl-9`}
                type={showPassword ? 'text' : 'password'}
                autoComplete={isNew ? 'new-password' : 'current-password'}
                required
                minLength={isNew ? 6 : 1}
                maxLength={128}
                value={field.state.value}
                onChange={(event) => field.handleChange(event.target.value)}
              />
            </span>
          </label>
        )}
      </form.Field>
      {isNew ? (
        <>
          <p className="-mt-3 text-xs text-muted">
            6～128 位，无需组合特殊字符。
          </p>
          <form.Field name="repeat">
            {(field) => (
              <label className="grid gap-2 text-sm font-medium">
                确认新密码
                <span className="relative block">
                  <LockKeyhole
                    size={16}
                    aria-hidden="true"
                    className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
                  />
                  <input
                    className={`${control} pl-9`}
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    minLength={6}
                    maxLength={128}
                    value={field.state.value}
                    onChange={(event) => field.handleChange(event.target.value)}
                  />
                </span>
              </label>
            )}
          </form.Field>
        </>
      ) : null}
      <button
        type="button"
        className="btn-ghost justify-self-start text-xs"
        aria-pressed={showPassword}
        onClick={() => setShowPassword(!showPassword)}
      >
        {showPassword ? (
          <EyeOff size={16} aria-hidden="true" />
        ) : (
          <Eye size={16} aria-hidden="true" />
        )}
        {showPassword ? '隐藏密码' : '显示密码'}
      </button>
      <ErrorNotice error={error} />
      <button className={button} disabled={submit.isPending || sending}>
        {submit.isPending
          ? '正在提交…'
          : mode === 'register'
            ? '注册并进入'
            : mode === 'reset'
              ? '重置密码'
              : mode === 'change'
                ? '修改密码并退出'
                : '登录'}
      </button>
    </form>
  )
}
