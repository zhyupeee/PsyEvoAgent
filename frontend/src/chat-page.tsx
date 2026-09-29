import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  ArrowUp,
  ArrowRight,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Square,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { getIdentity, request, RequestError } from './account-api'
import { ChatTimeline, turnLabels } from './chat-timeline'
import { modelFailure } from './model-settings'
import { Button } from './components/ui/button'
import { Textarea } from './components/ui/textarea'
import {
  BranchActions,
  FeedbackForm,
  notifyPrivateChange,
  SessionActions,
  SessionList,
  TurnHistory,
} from './history-page'
import {
  preferencesQuery,
  runSchema,
  sessionSchema,
  terminal,
  titlePending,
} from './support-api'

const SIDEBAR_COLLAPSED_KEY = 'psyevo.chat-sidebar-collapsed'

export function ChatPage({ sessionId }: { sessionId?: string }) {
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [blockedSessions, setBlockedSessions] = useState<Set<string>>(
    () => new Set(),
  )
  const blockSession = (id: string) =>
    setBlockedSessions((previous) => new Set(previous).add(id))
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    typeof window === 'undefined'
      ? false
      : window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true',
  )
  const toggleCollapsed = () =>
    setSidebarCollapsed((value) => {
      const next = !value
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next))
      } catch {
        // localStorage 不可用时折叠状态仅在本次会话内生效
      }
      return next
    })
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
  const client = useQueryClient()
  const key = useRef<string | null>(null)
  const create = useMutation({
    mutationFn: async () => {
      key.current ??= crypto.randomUUID()
      const session = await request('/sessions', sessionSchema, {
        method: 'POST',
        body: {},
        csrf: identity.data?.csrf_token,
        key: key.current,
      })
      key.current = null
      setSidebarOpen(false)
      await client.invalidateQueries({ queryKey: ['sessions'] })
      await navigate({
        to: '/chat/$sessionId',
        params: { sessionId: session.id },
      })
    },
  })
  return (
    <div
      className="support-content chat-workspace group/workspace relative flex min-h-0 w-full flex-1 overflow-hidden"
      data-sidebar-open={sidebarOpen}
      data-sidebar-collapsed={sidebarCollapsed}
    >
      <div className="chat-sidebar-inner sidebar-rail" data-sidebar-motion>
        <aside
          id="chat-sidebar"
          data-sidebar-motion
          className="chat-sidebar sidebar-panel z-20 flex flex-col gap-4 overflow-y-auto border-r border-line bg-paper p-3 side:z-auto"
          aria-label="会话列表"
        >
          <div className="sidebar-heading flex items-center justify-between gap-2 px-1">
            <p className="eyebrow">留给自己的空间</p>
            <button
              className="sidebar-toggle btn-ghost side:hidden"
              onClick={() => setSidebarOpen(false)}
            >
              收起会话
            </button>
          </div>
          <Button
            className="primary btn-primary min-h-10 w-full gap-1.5 rounded-xl px-4 shadow-sm transition-all duration-150 hover:shadow-md hover:brightness-[1.04] active:translate-y-px active:shadow-sm"
            disabled={create.isPending || !identity.data}
            onClick={() => create.mutate()}
          >
            <span className="relative text-center leading-5">
              <Plus
                size={18}
                className="absolute top-1/2 right-full mr-1.5 -translate-y-1/2"
                aria-hidden="true"
              />
              新建对话
            </span>
          </Button>
          {create.isError ? (
            <p role="alert" className="text-sm text-danger">
              未能建立对话，请重试。
            </p>
          ) : null}
          <SessionList
            csrf={identity.data?.csrf_token ?? ''}
            currentSessionId={sessionId}
            onBlocking={blockSession}
            onSelect={() => setSidebarOpen(false)}
          />
        </aside>
      </div>
      <div className="chat-layout flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto bg-white [overflow-anchor:none]">
        <header className="support-header flex min-h-14 flex-shrink-0 flex-wrap items-center gap-1 border-b border-line px-3 py-1.5">
          <button
            className="sidebar-toggle btn-ghost side:hidden"
            aria-expanded={sidebarOpen}
            aria-controls="chat-sidebar"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            历史对话
          </button>
          <button
            className="btn-icon hidden side:inline-flex"
            aria-expanded={!sidebarCollapsed}
            aria-controls="chat-sidebar"
            aria-label={sidebarCollapsed ? '展开会话列表' : '折叠会话列表'}
            onClick={toggleCollapsed}
          >
            {sidebarCollapsed ? (
              <PanelLeftOpen size={18} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={18} aria-hidden="true" />
            )}
          </button>
          {sessionId ? (
            <Link to="/chat" className="btn-ghost">
              ← 返回对话列表
            </Link>
          ) : (
            <h1 className="px-2 text-base font-semibold">对话</h1>
          )}
          <Link
            to="/resources"
            search={{ tab: 'support' }}
            className="btn-ghost ml-auto"
          >
            现实支持
          </Link>
        </header>
        {sessionId ? (
          <Conversation
            key={sessionId}
            sessionId={sessionId}
            csrf={identity.data?.csrf_token ?? ''}
            blocking={blockedSessions.has(sessionId)}
            onBlocking={() => blockSession(sessionId)}
          />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-6 pt-8 pb-5 side:px-10">
            <section className="chat-welcome m-auto flex w-full max-w-[680px] shrink-0 flex-col items-center py-12 text-center side:py-16">
              <div
                aria-hidden="true"
                className="mb-7 grid h-16 w-16 place-items-center rounded-[22px] bg-accent/70 text-status"
              >
                <MessageCircle size={29} strokeWidth={1.5} />
              </div>
              <div>
                <p className="mb-3 text-xs font-medium tracking-[0.14em] text-muted">
                  留一点空间，给此刻的自己
                </p>
                <h2 className="text-[clamp(1.75rem,3vw,2.5rem)] leading-snug font-semibold tracking-tight text-ink">
                  今天，想聊些什么？
                </h2>
                <p className="mt-5 text-sm leading-7 text-muted side:text-base side:leading-8">
                  不必想好怎么说，也不必急着找到答案。
                  <br />
                  从此刻最在意的一件小事开始。
                </p>
              </div>
              <div className="chat-welcome-actions mt-8 flex flex-col items-center gap-3">
                <button
                  className="primary btn btn-primary min-h-12 gap-3 rounded-full px-7 text-sm shadow-[0_3px_12px_-4px_rgba(37,121,198,0.4)]"
                  disabled={create.isPending || !identity.data}
                  onClick={() => create.mutate()}
                >
                  开始一次对话
                  <ArrowRight size={18} aria-hidden="true" />
                </button>
                {create.isError ? (
                  <p role="alert" className="text-sm text-danger">
                    未能建立对话，请重试。
                  </p>
                ) : null}
                <Link to="/resources" className="btn-ghost text-xs">
                  也可以先看看支持资源 →
                </Link>
              </div>
            </section>

            <footer className="secondary-link mx-auto flex w-full max-w-[760px] shrink-0 flex-col items-center gap-2 pt-6 text-center text-xs leading-5 text-muted">
              <p>提供一般支持，不能替代专业咨询或诊断。</p>
              <Link
                to="/me"
                search={{ section: 'data' }}
                className="rounded px-2 py-1 text-muted transition-colors hover:text-ink"
              >
                删除处理记录
              </Link>
            </footer>
          </div>
        )}
      </div>
    </div>
  )
}

type Attempt = { text: string; id: string; draft?: string; grant?: string }
function Conversation({
  sessionId,
  csrf,
  blocking,
  onBlocking,
}: {
  sessionId: string
  csrf: string
  blocking: boolean
  onBlocking: () => void
}) {
  const client = useQueryClient()
  const preferences = useQuery(preferencesQuery)
  const session = useQuery({
    queryKey: ['session', sessionId],
    queryFn: ({ signal }) =>
      request('/sessions/' + sessionId, sessionSchema, { signal }),
    refetchInterval: (query) =>
      !query.state.error &&
      query.state.dataUpdateCount < 180 &&
      query.state.data &&
      titlePending(query.state.data)
        ? 2000
        : false,
  })
  const queryKey = ['current-run', sessionId]
  const current = useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      request(`/sessions/${sessionId}/current-run`, runSchema.nullable(), {
        signal,
      }),
    refetchInterval: (query) =>
      query.state.data &&
      !terminal(query.state.data) &&
      query.state.data.status !== 'draft'
        ? 3000
        : false,
  })
  const run = current.isError || blocking ? null : current.data
  const active = !!run && ['queued', 'running'].includes(run.status)
  const [connection, setConnection] = useState('')
  const runId = run?.run_id
  useEffect(() => {
    if (run?.status === 'completed') {
      void client.invalidateQueries({ queryKey: ['session', sessionId] })
      void client.invalidateQueries({ queryKey: ['sessions'] })
    }
  }, [runId, run?.status, client, sessionId])
  useEffect(() => {
    if (session.data?.title_source === 'auto') {
      void client.invalidateQueries({ queryKey: ['sessions'] })
      notifyPrivateChange({ type: 'session-updated', sessionId })
    }
  }, [
    session.data?.title_revision,
    session.data?.title_source,
    client,
    sessionId,
  ])
  useEffect(() => {
    if (!runId || !active) return
    // SSE only invalidates the authorized read model; raw candidate deltas never enter the UI.
    const source = new EventSource(`/api/v1/runs/${runId}/events`)
    let cursor = 0
    for (const type of [
      'run.started',
      'message.delta',
      'run.completed',
      'run.failed',
      'run.cancelled',
    ]) {
      source.addEventListener(type, (raw) => {
        const event = raw as MessageEvent<string>
        const id = Number(event.lastEventId)
        if (!Number.isSafeInteger(id) || id <= cursor) return
        cursor = id
        setConnection('已连接')
        void client.invalidateQueries({ queryKey: ['current-run', sessionId] })
      })
    }
    source.onerror = () => {
      // EventSource hides HTTP 410. Recover through the same authorized snapshot, never start.
      source.close()
      setConnection('连接中断，正在核对运行状态。不会自动重新发送。')
      void client.invalidateQueries({ queryKey: ['current-run', sessionId] })
    }
    return () => source.close()
  }, [runId, active, client, sessionId])
  const attempt = useRef<Attempt | null>(null)
  const send = useMutation({
    mutationFn: async (text: string) => {
      recover.reset()
      if (!session.data) throw new Error('会话尚未就绪。')
      const parsed = z
        .string()
        .trim()
        .min(1)
        .max(4000)
        .refine((v) => !v.includes('\0'))
        .parse(text)
      if (attempt.current && attempt.current.text !== parsed)
        throw new Error('上次发送状态尚未确认，请先重试原消息或查询状态。')
      const pending = attempt.current ?? {
        text: parsed,
        id: crypto.randomUUID(),
      }
      attempt.current = pending
      const write = <T,>(
        path: string,
        schema: z.ZodType<T>,
        body: unknown,
        step: string,
      ) =>
        request(path, schema, {
          method: 'POST',
          csrf,
          body,
          key: pending.id + step,
        })
      // Preserve the previous completed turn before current-run advances.
      await client.refetchQueries({ queryKey: ['timeline', sessionId] })
      if (!pending.draft) {
        const draft = await write(
          '/run-drafts',
          runSchema,
          {
            context_type: 'conversation',
            session_id: sessionId,
            expected_session_version: session.data.version,
          },
          '-draft',
        )
        pending.draft = draft.run_id
      }
      if (!pending.grant) {
        const grant = await write(
          '/context-grants',
          z.object({ id: z.string() }),
          {
            run_id: pending.draft,
            source_type: 'conversation',
            source_id: sessionId,
            source_version: session.data.version,
            purpose: 'current_run',
          },
          '-grant',
        )
        pending.grant = grant.id
      }
      await write(
        `/runs/${pending.draft}/start`,
        runSchema,
        {
          expected_version: 1,
          expected_session_version: session.data.version,
          input: { message: pending.text },
          client_message_id: pending.id,
          grant_ids: [pending.grant],
        },
        '-start',
      )
      attempt.current = null
      form.reset()
      await client.invalidateQueries({ queryKey })
      await client.invalidateQueries({ queryKey: ['timeline', sessionId] })
      notifyPrivateChange({ type: 'session-updated', sessionId })
    },
    onError: async (error) => {
      // Another tab may have accepted a run before this draft was created.
      // Recover its stop/status controls even though our send did not succeed.
      if (error instanceof RequestError && error.code === 'run_active')
        await client.invalidateQueries({ queryKey })
    },
  })
  const form = useForm({
    defaultValues: { message: '' },
    onSubmit: async ({ value }) => {
      await send.mutateAsync(value.message).catch(() => undefined)
    },
  })
  useEffect(() => {
    const pending = attempt.current
    if (
      !pending?.draft ||
      run?.run_id !== pending.draft ||
      run.status === 'draft' ||
      run.input_text !== pending.text ||
      send.isPending
    )
      return
    attempt.current = null
    send.reset()
    if (form.state.values.message.trim() === pending.text) form.reset()
  }, [run, send, form])
  const cancel = useMutation({
    mutationFn: async () => {
      if (!runId) return
      const latest = await request('/runs/' + runId, runSchema)
      await request(`/runs/${runId}/cancel`, runSchema, {
        method: 'POST',
        csrf,
        body: { expected_version: latest.version },
      })
      await client.invalidateQueries({ queryKey })
    },
  })
  const recover = useMutation({
    mutationFn: async () => {
      const pending = attempt.current
      const result = await current.refetch({ throwOnError: true })
      await client.invalidateQueries({ queryKey: ['timeline', sessionId] })
      const latest = result.data
      if (
        !latest ||
        latest.status === 'draft' ||
        (pending && latest.run_id !== pending.draft)
      )
        return '尚未确认发送成功。请点击“重试原消息”继续发送。'
      if (latest.status === 'failed' || latest.status === 'interrupted')
        return '已确认本次回答失败。可在消息下方点击“重新生成”。'
      return `已更新：${turnLabels[latest.status]}。`
    },
  })
  if (session.isError || current.isError)
    return (
      <section className="grid flex-1 place-items-center p-8">
        <div className="card grid max-w-[420px] justify-items-start gap-3">
          <h1 className="text-lg font-semibold">对话暂不可用</h1>
          <p role="alert" className="text-sm text-danger">
            无法读取或无权访问，内容已隐藏。
          </p>
          <button
            className="btn"
            onClick={() => {
              void session.refetch()
              void current.refetch()
            }}
          >
            查询状态
          </button>
        </div>
      </section>
    )
  return (
    <>
      <div className="conversation-heading relative flex flex-shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-2 side:px-5">
        <h1 className="chat-title min-w-0 flex-1 truncate text-lg font-semibold">
          {blocking || preferences.data?.display_preferences.hide_titles
            ? '对话'
            : (session.data?.title ?? '正在读取…')}
        </h1>
        <div className="conversation-actions flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
          {!blocking ? (
            <TurnHistory sessionId={sessionId} currentId={run?.run_id} />
          ) : null}
          {session.data ? (
            <SessionActions
              session={session.data}
              csrf={csrf}
              active={!!run && !terminal(run)}
              onBlocking={onBlocking}
            />
          ) : null}
        </div>
      </div>
      {blocking ? (
        <p role="alert" className="px-5 py-3 text-sm text-danger">
          内容已隐藏。请在删除处理记录中核对结果，未确认时可重试原删除请求。
        </p>
      ) : (
        <>
          {session.data?.status === 'archived' ? (
            <p className="px-5 pt-2 text-sm text-muted">
              此对话已归档，恢复后可继续发送。
            </p>
          ) : null}
          <ChatTimeline sessionId={sessionId} current={run}>
            <p role="status" className="mb-2 text-sm text-muted">
              {run ? turnLabels[run.status] : ''}
              {active ? ` · ${connection}` : ''}
            </p>
            {run && ['failed', 'interrupted'].includes(run.status) ? (
              <p role="alert" className="mb-2 text-sm text-danger">
                本次回答未完成，输入已保留。可以点击下方“重新生成”重试。
                {run.stop_reason ? ` ${modelFailure(run.stop_reason)}` : ''}
              </p>
            ) : null}
            <div className="response-tools mb-3 flex flex-wrap items-start gap-x-4 gap-y-2">
              {run && terminal(run) ? (
                <FeedbackForm
                  key={`feedback-${run.run_id}`}
                  runId={run.run_id}
                  csrf={csrf}
                />
              ) : null}
              {run?.input_id && !active && session.data?.status === 'active' ? (
                <BranchActions
                  key={`branch-${run.run_id}`}
                  run={run}
                  sessionId={sessionId}
                  sessionVersion={session.data.version}
                  csrf={csrf}
                />
              ) : null}
            </div>
          </ChatTimeline>
          <form
            className="composer mx-auto w-full max-w-[800px] flex-shrink-0 px-3 pb-3 side:px-5"
            onSubmit={(e) => {
              e.preventDefault()
              if (
                !send.isPending &&
                !active &&
                session.data?.status === 'active' &&
                !(run?.status === 'draft' && run.input_id)
              )
                void form.handleSubmit()
            }}
          >
            {send.isError ? (
              <p role="alert" className="mb-2 text-sm text-danger">
                发送未确认，输入已保留。服务可能尚未配置；重试原消息不会重复创建运行。
              </p>
            ) : null}
            {cancel.isError ? (
              <p role="alert" className="mb-2 text-sm text-danger">
                停止未确认，请检查发送状态后重试。
              </p>
            ) : null}
            <div className="rounded-3xl border border-line bg-white px-4 pt-3 pb-2 shadow-sm transition focus-within:border-status focus-within:ring-2 focus-within:ring-accent">
              <form.Field name="message">
                {(field) => (
                  <>
                    <label htmlFor="chat-message-input" className="sr-only">
                      想说的事
                    </label>
                    <Textarea
                      id="chat-message-input"
                      disabled={!session.data || !csrf}
                      maxLength={4000}
                      rows={2}
                      placeholder="想说的事…"
                      value={field.state.value}
                      onChange={(e) => {
                        field.handleChange(e.target.value)
                        e.target.style.height = 'auto'
                        e.target.style.height =
                          Math.min(e.target.scrollHeight, 200) + 'px'
                      }}
                      aria-describedby="message-limit"
                      className="block max-h-[200px] min-h-[52px] w-full resize-none! rounded-none border-0 bg-transparent px-1 py-1 text-[0.95em] leading-normal outline-none focus:border-0 focus:shadow-none"
                    />
                    <div className="mt-1 flex items-center gap-3">
                      <span id="message-limit" className="text-xs text-muted">
                        {field.state.value.length} / 4000 · Enter 换行
                      </span>
                      <div className="ml-auto flex items-center gap-2">
                        {send.isError || cancel.isError ? (
                          <button
                            type="button"
                            className="btn-ghost text-xs"
                            disabled={recover.isPending}
                            onClick={() => recover.mutate()}
                          >
                            {recover.isPending ? '正在检查…' : '检查发送状态'}
                          </button>
                        ) : null}
                        {active ? (
                          <button
                            type="button"
                            aria-label={
                              cancel.isPending ? '正在确认停止…' : '停止生成'
                            }
                            disabled={cancel.isPending}
                            onClick={() => cancel.mutate()}
                            className="grid h-9 w-9 place-items-center rounded-full bg-ink text-white transition enabled:hover:bg-ink/85 disabled:opacity-40"
                          >
                            <Square
                              size={13}
                              aria-hidden="true"
                              fill="currentColor"
                            />
                          </button>
                        ) : (
                          <form.Subscribe
                            selector={(state) => state.values.message}
                          >
                            {(message) => (
                              <button
                                className="primary grid h-9 w-9 place-items-center rounded-full bg-status text-white transition enabled:hover:bg-status-strong disabled:opacity-40"
                                aria-label={
                                  send.isPending
                                    ? '正在提交…'
                                    : send.isError
                                      ? '重试原消息'
                                      : '发送'
                                }
                                disabled={
                                  send.isPending ||
                                  !session.data ||
                                  !message.trim() ||
                                  session.data.status !== 'active' ||
                                  !!(run?.status === 'draft' && run.input_id)
                                }
                              >
                                <ArrowUp size={18} aria-hidden="true" />
                              </button>
                            )}
                          </form.Subscribe>
                        )}
                      </div>
                      <Link
                        to="/resources/exercises/$exerciseId"
                        params={{ exerciseId: 'attention' }}
                        search={{ from: sessionId }}
                        className="btn-ghost -order-1 px-2 text-xs"
                      >
                        独立练习
                      </Link>
                    </div>
                  </>
                )}
              </form.Field>
            </div>
            <p aria-live="polite" className="mt-1.5 px-2 text-xs text-muted">
              {recover.isPending
                ? '正在检查发送状态…'
                : recover.isError
                  ? '暂时无法检查状态，请稍后重试。'
                  : recover.data}
            </p>
          </form>
        </>
      )}
    </>
  )
}
