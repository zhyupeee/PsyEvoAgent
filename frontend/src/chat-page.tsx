import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { getIdentity, request } from './account-api'
import { ChatTimeline, turnLabels } from './chat-timeline'
import { modelFailure } from './model-settings'
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

export function ChatPage({ sessionId }: { sessionId?: string }) {
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)
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
      className="support-content chat-workspace"
      data-sidebar-open={sidebarOpen}
    >
      <aside id="chat-sidebar" className="chat-sidebar" aria-label="会话列表">
        <div className="sidebar-heading">
          <p className="eyebrow">留给自己的空间</p>
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(false)}
          >
            收起会话
          </button>
        </div>
        <button
          className="primary"
          disabled={create.isPending || !identity.data}
          onClick={() => create.mutate()}
        >
          新建对话
        </button>
        {create.isError ? <p role="alert">未能建立对话，请重试。</p> : null}
        <SessionList onSelect={() => setSidebarOpen(false)} />
      </aside>
      <div className="chat-layout">
        <header className="support-header">
          <button
            className="sidebar-toggle"
            aria-expanded={sidebarOpen}
            aria-controls="chat-sidebar"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            历史对话
          </button>
          {sessionId ? <Link to="/chat">← 返回对话列表</Link> : <h1>对话</h1>}
          <Link to="/resources" search={{ tab: 'support' }}>
            现实支持
          </Link>
        </header>
        {sessionId ? (
          <Conversation
            key={sessionId}
            sessionId={sessionId}
            csrf={identity.data?.csrf_token ?? ''}
          />
        ) : (
          <>
            <section className="chat-welcome">
              <div>
                <p className="eyebrow">留一点空间，给此刻的自己</p>
                <h2>今天，想聊些什么？</h2>
                <p>
                  可以从现在最在意的一件事说起。提供一般支持，不能替代专业咨询或诊断。
                </p>
              </div>
              <div className="chat-welcome-actions">
                <button
                  className="primary"
                  disabled={create.isPending || !identity.data}
                  onClick={() => create.mutate()}
                >
                  开始一次对话
                </button>
                {create.isError ? (
                  <p role="alert">未能建立对话，请重试。</p>
                ) : null}
                <Link to="/resources">也可以先看看支持资源 →</Link>
              </div>
            </section>

            <p className="secondary-link">
              <Link to="/me" search={{ section: 'data' }}>
                删除处理记录
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}

type Attempt = { text: string; id: string; draft?: string; grant?: string }
function Conversation({
  sessionId,
  csrf,
}: {
  sessionId: string
  csrf: string
}) {
  const client = useQueryClient()
  const [blocking, setBlocking] = useState(false)
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
      <section>
        <h1>对话暂不可用</h1>
        <p role="alert">无法读取或无权访问，内容已隐藏。</p>
        <button
          onClick={() => {
            void session.refetch()
            void current.refetch()
          }}
        >
          查询状态
        </button>
      </section>
    )
  return (
    <>
      <div className="conversation-heading">
        <h1 className="chat-title">
          {blocking || preferences.data?.display_preferences.hide_titles
            ? '对话'
            : (session.data?.title ?? '正在读取…')}
        </h1>
        <div className="conversation-actions">
          {!blocking ? (
            <TurnHistory sessionId={sessionId} currentId={run?.run_id} />
          ) : null}
          {session.data ? (
            <SessionActions
              session={session.data}
              csrf={csrf}
              active={!!run && !terminal(run)}
              onBlocking={() => setBlocking(true)}
            />
          ) : null}
        </div>
      </div>
      {blocking ? (
        <p role="alert">
          内容已隐藏。请在删除处理记录中核对结果，未确认时可重试原删除请求。
        </p>
      ) : (
        <>
          {session.data?.status === 'archived' ? (
            <p>此对话已归档，恢复后可继续发送。</p>
          ) : null}
          <ChatTimeline sessionId={sessionId} current={run}>
            <p role="status">
              {run ? turnLabels[run.status] : ''}
              {active ? ` · ${connection}` : ''}
            </p>
            {run && ['failed', 'interrupted'].includes(run.status) ? (
              <p role="alert">
                本次回答未完成，输入已保留。可以点击下方“重新生成”重试。
                {run.stop_reason ? ` ${modelFailure(run.stop_reason)}` : ''}
              </p>
            ) : null}
            <div className="response-tools">
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
            className="composer"
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
            <form.Field name="message">
              {(field) => (
                <label>
                  想说的事
                  <textarea
                    disabled={!session.data || !csrf}
                    maxLength={4000}
                    rows={2}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    aria-describedby="message-limit"
                  />
                  <span id="message-limit" className="text-sm text-muted">
                    {field.state.value.length} / 4000 · Enter 换行
                  </span>
                </label>
              )}
            </form.Field>
            {send.isError ? (
              <p role="alert">
                发送未确认，输入已保留。服务可能尚未配置；重试原消息不会重复创建运行。
              </p>
            ) : null}
            {cancel.isError ? (
              <p role="alert">停止未确认，请检查发送状态后重试。</p>
            ) : null}
            <div className="flex flex-wrap gap-3">
              {active ? (
                <button
                  type="button"
                  disabled={cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  {cancel.isPending ? '正在确认停止…' : '停止生成'}
                </button>
              ) : (
                <form.Subscribe selector={(state) => state.values.message}>
                  {(message) => (
                    <button
                      className="primary"
                      disabled={
                        send.isPending ||
                        !session.data ||
                        !message.trim() ||
                        session.data.status !== 'active' ||
                        !!(run?.status === 'draft' && run.input_id)
                      }
                    >
                      {send.isPending
                        ? '正在提交…'
                        : send.isError
                          ? '重试原消息'
                          : '发送'}
                    </button>
                  )}
                </form.Subscribe>
              )}
              {send.isError || cancel.isError ? (
                <button
                  type="button"
                  disabled={recover.isPending}
                  onClick={() => recover.mutate()}
                >
                  {recover.isPending ? '正在检查…' : '检查发送状态'}
                </button>
              ) : null}
              <Link
                to="/resources/exercises/$exerciseId"
                params={{ exerciseId: 'attention' }}
                search={{ from: sessionId }}
              >
                独立练习
              </Link>
            </div>
            <p aria-live="polite" className="text-sm text-muted">
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
