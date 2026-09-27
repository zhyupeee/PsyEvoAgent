import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useRef, useState } from 'react'
import { z } from 'zod'
import { request } from './account-api'
import {
  preferencesQuery,
  runSchema,
  sessionSchema,
  type Run,
} from './support-api'

export const privateChangeOrigin = crypto.randomUUID()

export const privateChangeSchema = z.discriminatedUnion('type', [
  z.object({
    origin: z.string(),
    type: z.literal('session-updated'),
    sessionId: z.string(),
  }),
  z.object({
    origin: z.string(),
    type: z.literal('session-deleted'),
    sessionId: z.string(),
  }),
  z.object({ origin: z.string(), type: z.literal('signed-out') }),
])

type PrivateChange = z.infer<typeof privateChangeSchema>

export function notifyPrivateChange(
  change:
    | Omit<Extract<PrivateChange, { sessionId: string }>, 'origin'>
    | { type: 'signed-out' },
) {
  const channel = new BroadcastChannel('psyevo-private-change')
  channel.postMessage({ ...change, origin: privateChangeOrigin })
  channel.close()
}

export function SessionList() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('active')
  const [cursor, setCursor] = useState<string | null>(null)
  const preferences = useQuery(preferencesQuery)
  const form = useForm({
    defaultValues: { search: '' },
    onSubmit: ({ value }) => {
      setSearch(value.search.trim())
      setCursor(null)
    },
  })
  const list = useQuery({
    queryKey: ['sessions', search, status, cursor],
    queryFn: ({ signal }) =>
      request(
        '/sessions?' +
          new URLSearchParams({
            q: search,
            status,
            ...(cursor ? { cursor } : {}),
          }),
        z.object({
          items: z.array(sessionSchema),
          next_cursor: z.string().nullable(),
        }),
        { signal },
      ),
  })
  return (
    <details className="history-panel" open>
      <summary>我的对话</summary>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          void form.handleSubmit()
        }}
      >
        <form.Field name="search">
          {(field) => (
            <label>
              搜索标题
              <input
                maxLength={120}
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
              />
            </label>
          )}
        </form.Field>
        <button>搜索</button>
        <label>
          会话范围
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setCursor(null)
            }}
          >
            <option value="active">未归档</option>
            <option value="archived">已归档</option>
          </select>
        </label>
      </form>
      {list.isPending ? <p>正在读取…</p> : null}
      {list.isError ? (
        <p role="alert">
          列表未能读取。
          <button onClick={() => void list.refetch()}>重试列表</button>
        </p>
      ) : null}
      {!list.isError && list.data?.items.length === 0 ? (
        <p>没有匹配的对话。</p>
      ) : null}
      <ul className="session-list">
        {!list.isError
          ? list.data?.items.map((item) => (
              <li key={item.id}>
                <Link to="/chat/$sessionId" params={{ sessionId: item.id }}>
                  {preferences.data?.display_preferences.hide_titles
                    ? '对话'
                    : item.title}
                </Link>
                <small>
                  {item.status === 'archived' ? '已归档' : '未归档'}
                </small>
              </li>
            ))
          : null}
      </ul>
      {cursor ? (
        <button onClick={() => setCursor(null)}>返回首批</button>
      ) : null}
      {list.data?.next_cursor ? (
        <button onClick={() => setCursor(list.data!.next_cursor)}>
          下一批对话
        </button>
      ) : null}
    </details>
  )
}

const deletionSchema = z.object({
  deletion_id: z.string(),
  target: z.string(),
  version: z.number(),
  status: z.string(),
  completed_steps: z.array(z.string()),
  remaining_steps: z.array(z.string()),
  retryable: z.boolean(),
})
export function DeletionReceipts({ csrf }: { csrf: string }) {
  const client = useQueryClient()
  const jobs = useQuery({
    queryKey: ['deletions', csrf],
    enabled: Boolean(csrf),
    queryFn: ({ signal }) =>
      request('/deletion-jobs', z.object({ items: z.array(deletionSchema) }), {
        signal,
      }),
  })
  const retry = useMutation({
    mutationFn: async (job: z.infer<typeof deletionSchema>) => {
      await request(`/deletion-jobs/${job.deletion_id}/retry`, deletionSchema, {
        method: 'POST',
        csrf,
        body: { expected_version: job.version },
      })
      await client.invalidateQueries({ queryKey: ['deletions'] })
    },
  })
  const names: Record<string, string> = {
    online_blocked: '阻断访问',
    messages: '消息正文',
    events: '流与互动事件',
    feedback: '关联反馈',
    source_links: '来源关联',
  }
  return (
    <details className="history-panel">
      <summary>删除处理记录</summary>
      {jobs.isError ? (
        <p role="alert">
          删除状态读取失败。
          <button onClick={() => void jobs.refetch()}>查询删除状态</button>
        </p>
      ) : null}
      {retry.isError ? <p role="alert">清理重试未确认，请查询状态。</p> : null}
      {!jobs.isError && !jobs.data?.items.length ? <p>暂无删除记录。</p> : null}
      {!jobs.isError
        ? jobs.data?.items.map((job) => (
            <article key={job.deletion_id} className="deletion-receipt">
              <p>
                {job.status === 'completed'
                  ? '本应用在线内容清理完成'
                  : '已阻断访问，清理尚未完成'}
              </p>
              <p className="text-sm">回执：{job.deletion_id}</p>
              <p>
                已处理：
                {job.completed_steps
                  .map((step) => names[step] ?? step)
                  .join('、')}
              </p>
              {job.remaining_steps.length ? (
                <p>
                  待处理：
                  {job.remaining_steps
                    .map((step) => names[step] ?? step)
                    .join('、')}
                </p>
              ) : null}
              <p className="text-sm text-muted">
                本次处理本应用保存的在线内容，保留无正文的删除标记和用量记录。已自行复制的内容不在此范围内。
              </p>
              {job.status !== 'completed' ? (
                <button
                  disabled={retry.isPending}
                  onClick={() => retry.mutate(job)}
                >
                  重试清理
                </button>
              ) : null}
            </article>
          ))
        : null}
    </details>
  )
}

export function SessionActions({
  session,
  csrf,
  active,
  onBlocking,
}: {
  session: z.infer<typeof sessionSchema>
  csrf: string
  active: boolean
  onBlocking: () => void
}) {
  const client = useQueryClient()
  const dialog = useRef<HTMLDialogElement>(null)
  const deletionKey = useRef(crypto.randomUUID())
  const rename = useForm({
    defaultValues: { title: session.title },
    onSubmit: async ({ value }) => {
      await change
        .mutateAsync({
          title: value.title,
        })
        .catch(() => undefined)
    },
  })
  const change = useMutation({
    mutationFn: async (patch: { title?: string; status?: string }) => {
      const body = {
        ...patch,
        ...(patch.title !== undefined
          ? { title: z.string().trim().min(1).max(120).parse(patch.title) }
          : {}),
        expected_version: session.version,
      }
      await request('/sessions/' + session.id, sessionSchema, {
        method: 'PATCH',
        csrf,
        body,
      })
      await client.invalidateQueries()
      notifyPrivateChange({ type: 'session-updated', sessionId: session.id })
    },
  })
  const remove = useMutation({
    mutationFn: async () => {
      onBlocking()
      await request('/sessions/' + session.id, deletionSchema, {
        method: 'DELETE',
        csrf,
        key: deletionKey.current,
        body: { expected_version: session.version, confirmed: true },
      })
      await client.cancelQueries()
      client.clear()
      notifyPrivateChange({ type: 'session-deleted', sessionId: session.id })
      window.location.replace('/chat')
    },
  })
  return (
    <section className="session-actions" aria-label="会话管理">
      <details>
        <summary>管理此对话</summary>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            void rename.handleSubmit()
          }}
        >
          <rename.Field name="title">
            {(field) => (
              <label>
                对话标题
                <input
                  maxLength={120}
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
              </label>
            )}
          </rename.Field>
          <button disabled={active || change.isPending}>保存标题</button>
          <button
            type="button"
            disabled={active || change.isPending}
            onClick={() =>
              change.mutate({
                status: session.status === 'archived' ? 'active' : 'archived',
              })
            }
          >
            {session.status === 'archived' ? '恢复归档' : '归档对话'}
          </button>
          <button type="button" onClick={() => dialog.current?.showModal()}>
            删除会话
          </button>
        </form>
        {change.isError ? (
          <p role="alert">
            修改未保存。运行未结束或版本已变化，请查询状态后重试。
          </p>
        ) : null}
        {change.isSuccess ? <p>会话信息已保存。</p> : null}
      </details>
      <dialog
        ref={dialog}
        className="confirm-dialog"
        aria-labelledby="delete-title"
      >
        <h2 id="delete-title">确认删除此会话？</h2>
        <p>
          将立即停止相关运行并阻断访问，清理消息、历史分支、事件及关联反馈。删除后无法恢复。
        </p>
        <p>完成情况可在“删除处理记录”中查询。</p>
        {remove.isError ? (
          <p role="alert">
            删除状态尚未确认。请重试原请求，或返回对话列表查询删除处理记录。
          </p>
        ) : null}
        <div className="flex flex-wrap gap-3">
          <button
            autoFocus
            disabled={remove.isPending}
            onClick={() => dialog.current?.close()}
          >
            暂不删除
          </button>
          <button
            className="primary"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? '正在处理…' : '确认删除'}
          </button>
        </div>
      </dialog>
    </section>
  )
}

export function TurnHistory({
  sessionId,
  currentId,
}: {
  sessionId: string
  currentId?: string
}) {
  const [cursor, setCursor] = useState<string | null>(null)
  const history = useQuery({
    queryKey: ['history', sessionId, currentId, cursor],
    queryFn: ({ signal }) =>
      request(
        `/sessions/${sessionId}/history?` +
          new URLSearchParams(cursor ? { cursor } : {}),
        z.object({
          items: z.array(runSchema),
          next_cursor: z.string().nullable(),
        }),
        { signal },
      ),
  })
  return (
    <details className="history-panel">
      <summary>历史轮次与旧分支</summary>
      {history.isError ? (
        <p role="alert">
          历史暂不可用。
          <button onClick={() => void history.refetch()}>重试历史</button>
        </p>
      ) : null}
      {!history.isError
        ? history.data?.items
            .filter((item) => item.run_id !== currentId)
            .map((item) => (
              <article className="history-turn" key={item.run_id}>
                <p className="text-sm text-muted">
                  {item.is_current ? '历史轮次' : '旧分支 · 不用于当前回答'} ·
                  输入版本 {item.input_version ?? '—'}
                </p>
                <p className="whitespace-pre-wrap">{item.input_text}</p>
                <p className="whitespace-pre-wrap">{item.output?.text}</p>
              </article>
            ))
        : null}
      {cursor ? (
        <button onClick={() => setCursor(null)}>最新历史</button>
      ) : null}
      {history.data?.next_cursor ? (
        <button onClick={() => setCursor(history.data!.next_cursor)}>
          更早历史
        </button>
      ) : null}
    </details>
  )
}

export function FeedbackForm({ runId, csrf }: { runId: string; csrf: string }) {
  const pending = useRef<{ key: string; body: string } | null>(null)
  const schema = z.object({
    helpfulness: z.enum(['helpful', 'neutral', 'unhelpful', 'not_rated']),
    category: z.enum([
      'general',
      'misunderstood',
      'listen_only',
      'inappropriate',
    ]),
    comment: z
      .string()
      .max(1000)
      .refine((v) => !v.includes('\0')),
  })
  const save = useMutation({
    mutationFn: async (value: {
      helpfulness: string
      category: string
      comment: string
    }) => {
      const body = { ...schema.parse(value), run_id: runId }
      if (pending.current && pending.current.body !== JSON.stringify(body))
        throw new Error('请先确认原反馈')
      pending.current ??= {
        key: crypto.randomUUID(),
        body: JSON.stringify(body),
      }
      return request(
        '/feedback',
        z.object({ feedback_id: z.string(), status: z.literal('saved') }),
        { method: 'POST', csrf, key: pending.current.key, body },
      )
    },
  })
  const form = useForm({
    defaultValues: {
      helpfulness: 'not_rated',
      category: 'general',
      comment: '',
    },
    onSubmit: async ({ value }) => {
      await save.mutateAsync(value).catch(() => undefined)
    },
  })
  const panel = useRef<HTMLDetailsElement>(null)
  return (
    <details ref={panel} className="feedback-panel">
      <summary>反馈或纠正 · 可跳过</summary>
      <p className="text-sm text-muted">
        用于支持质量反馈和内部评测；不自动附上整段对话，也不会修改你的交流偏好。可不评价或取消。
      </p>
      {save.data ? (
        <p role="status">反馈已保存，回执：{save.data.feedback_id}</p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void form.handleSubmit()
          }}
        >
          <form.Field name="helpfulness">
            {(field) => (
              <label>
                这次回答
                <select
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                >
                  <option value="not_rated">不评价</option>
                  <option value="helpful">有帮助</option>
                  <option value="neutral">一般</option>
                  <option value="unhelpful">不合适</option>
                </select>
              </label>
            )}
          </form.Field>
          <form.Field name="category">
            {(field) => (
              <label>
                反馈类型
                <select
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                >
                  <option value="general">一般反馈</option>
                  <option value="misunderstood">这里误解了我</option>
                  <option value="listen_only">我只想倾听</option>
                  <option value="inappropriate">回答不合适</option>
                </select>
              </label>
            )}
          </form.Field>
          <form.Field name="comment">
            {(field) => (
              <label>
                补充说明（可选）
                <textarea
                  rows={3}
                  maxLength={1000}
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
              </label>
            )}
          </form.Field>
          {save.isError ? (
            <p role="alert">
              反馈未确认，未显示已保存。重试原反馈不会重复提交。
            </p>
          ) : null}
          <div className="flex gap-3">
            <button className="primary" disabled={save.isPending}>
              提交反馈
            </button>
            <button
              type="button"
              disabled={save.isPending}
              onClick={() => {
                form.reset()
                save.reset()
                pending.current = null
                if (panel.current) panel.current.open = false
              }}
            >
              取消反馈
            </button>
          </div>
        </form>
      )}
    </details>
  )
}

export function BranchActions({
  run,
  sessionId,
  sessionVersion,
  csrf,
}: {
  run: Run
  sessionId: string
  sessionVersion: number
  csrf: string
}) {
  const client = useQueryClient()
  const pending = useRef<{
    key: string
    text?: string
    kind: string
    draft?: Run
  } | null>(null)
  const mutate = useMutation({
    mutationFn: async ({ kind, text }: { kind: string; text?: string }) => {
      if (kind === 'revision')
        text = z
          .string()
          .trim()
          .min(1)
          .max(4000)
          .refine((value) => !value.includes('\0'))
          .parse(text)
      if (
        pending.current &&
        (pending.current.kind !== kind || pending.current.text !== text)
      )
        throw new Error('请先重试原操作')
      const attempt = pending.current ?? {
        key: crypto.randomUUID(),
        kind,
        text,
      }
      pending.current = attempt
      if (kind === 'regenerate') {
        await request(`/sessions/${sessionId}/runs`, runSchema, {
          method: 'POST',
          csrf,
          key: attempt.key,
          body: {
            kind,
            expected_session_version: sessionVersion,
            client_message_id: attempt.key,
            input: { source_message_id: run.input_id },
          },
        })
      } else {
        if (kind === 'revision' && !attempt.draft)
          attempt.draft = await request(
            `/sessions/${sessionId}/messages/${run.input_id}/revisions`,
            runSchema,
            {
              method: 'POST',
              csrf,
              key: attempt.key + '-revision',
              body: {
                content: text,
                expected_version: run.input_version,
              },
            },
          )
        const draft = attempt.draft ?? run
        await request(`/runs/${draft.run_id}/start`, runSchema, {
          method: 'POST',
          csrf,
          key: attempt.key + '-start',
          body: {
            expected_version: draft.version,
            expected_session_version: sessionVersion,
            client_message_id: attempt.key,
            input: { source_message_id: draft.input_id },
          },
        })
      }
      pending.current = null
      await client.invalidateQueries({ queryKey: ['current-run', sessionId] })
      await client.invalidateQueries({ queryKey: ['history', sessionId] })
      notifyPrivateChange({ type: 'session-updated', sessionId })
    },
  })
  const form = useForm({
    defaultValues: { content: run.input_text ?? '' },
    onSubmit: async ({ value }) => {
      await mutate
        .mutateAsync({ kind: 'revision', text: value.content })
        .catch(() => undefined)
    },
  })
  return (
    <section className="branch-actions" aria-label="输入修订">
      {run.status === 'draft' ? (
        <button
          disabled={mutate.isPending}
          onClick={() => mutate.mutate({ kind: 'start' })}
        >
          生成本分支回答
        </button>
      ) : (
        <>
          <button
            disabled={mutate.isPending}
            onClick={() => mutate.mutate({ kind: 'regenerate' })}
          >
            重新生成
          </button>
          <details>
            <summary>修订最后输入</summary>
            <p>运行结束后才能修订。新版本生成新回答，旧版本保留在历史中。</p>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                void form.handleSubmit()
              }}
            >
              <form.Field name="content">
                {(field) => (
                  <label>
                    修订内容
                    <textarea
                      maxLength={4000}
                      rows={4}
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </label>
                )}
              </form.Field>
              <button className="primary" disabled={mutate.isPending}>
                保存修订并生成
              </button>
            </form>
          </details>
        </>
      )}
      {mutate.isError ? (
        <p role="alert">
          操作未确认，保留原输入。请重试原操作或查询运行状态；活动运行不能修订。
        </p>
      ) : null}
    </section>
  )
}
