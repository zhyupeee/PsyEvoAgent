import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { getIdentity, request } from './account-api'
import {
  preferencesQuery,
  runSchema,
  sessionSchema,
  terminal,
} from './support-api'

export function ChatPage({ sessionId }: { sessionId?: string }) {
  const navigate = useNavigate()
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
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
      await navigate({
        to: '/chat/$sessionId',
        params: { sessionId: session.id },
      })
    },
  })
  return (
    <div className="support-content chat-layout">
      <header className="support-header">
        <Link to="/chat">对话</Link>
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
        <section className="support-empty">
          <p className="eyebrow">留一点空间，给此刻的自己</p>
          <h1>开始一次对话</h1>
          <p>
            可以从现在最在意的一件事说起。提供一般支持，不能替代专业咨询或诊断。
          </p>
          <p className="text-muted">
            当前真实对话服务尚未配置。可先查看资源或调整偏好。
          </p>
          <button
            className="primary"
            disabled={create.isPending || !identity.data}
            onClick={() => create.mutate()}
          >
            开始一次对话
          </button>
          {create.isError ? <p role="alert">未能建立对话，请重试。</p> : null}
          <Link to="/resources">也可以先看看支持资源 →</Link>
        </section>
      )}
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
  const preferences = useQuery(preferencesQuery)
  const session = useQuery({
    queryKey: ['session', sessionId],
    queryFn: ({ signal }) =>
      request('/sessions/' + sessionId, sessionSchema, { signal }),
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
  const run = current.isError ? null : current.data
  const active = !!run && ['queued', 'running'].includes(run.status)
  const [connection, setConnection] = useState('')
  const runId = run?.run_id
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
  const labels = {
    draft: '尚未发送',
    queued: '已接收，等待响应',
    running: '正在响应',
    completed: '已完成',
    cancelled: '已停止',
    failed: '本次响应失败',
    interrupted: '本次响应中断',
  }
  return (
    <>
      <h1 className="chat-title">
        {preferences.data?.display_preferences.hide_titles
          ? '对话'
          : (session.data?.title ?? '正在读取…')}
      </h1>
      <div className="message-area" aria-label="当前轮次">
        {!run?.input_text && !run?.output ? (
          <p className="text-muted">
            想说的可以写在下面。每条最多 4000
            字；可在“我的”里选择先倾听或一起想办法。
          </p>
        ) : null}
        {run?.input_text ? (
          <p className="message user-message">{run.input_text}</p>
        ) : null}
        {run?.output ? (
          <p className="message assistant-message">{run.output.text}</p>
        ) : null}
        <p role="status">
          {run ? labels[run.status] : ''}
          {active ? ` · ${connection}` : ''}
        </p>
        {run && ['failed', 'interrupted'].includes(run.status) ? (
          <p role="alert">
            未完成响应。输入保留在当前轮次，可核对状态后再次发送。
          </p>
        ) : null}
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          if (!send.isPending && !active) void form.handleSubmit()
        }}
      >
        <form.Field name="message">
          {(field) => (
            <label>
              想说的事
              <textarea
                maxLength={4000}
                rows={4}
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
          <p role="alert">停止未确认，请查询状态后重试。</p>
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
                  disabled={send.isPending || !session.data || !message.trim()}
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
          <button type="button" onClick={() => void current.refetch()}>
            查询运行状态
          </button>
          <Link
            to="/resources/exercises/$exerciseId"
            params={{ exerciseId: 'attention' }}
            search={{ from: sessionId }}
          >
            独立练习
          </Link>
        </div>
      </form>
    </>
  )
}
