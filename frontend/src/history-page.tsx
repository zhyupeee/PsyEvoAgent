import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { ChevronDown, Inbox, RotateCcw, Search, Trash2, X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { z } from 'zod'
import { request } from './account-api'
import { Button } from './components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from './components/ui/collapsible'
import { Textarea } from './components/ui/textarea'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from './components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './components/ui/select'
import { MarkdownMessage } from './markdown-message'
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
  z.object({ origin: z.string(), type: z.literal('records-deleted') }),
])

type PrivateChange = z.infer<typeof privateChangeSchema>

export function notifyPrivateChange(
  change:
    | Omit<Extract<PrivateChange, { sessionId: string }>, 'origin'>
    | { type: 'signed-out' | 'records-deleted' },
) {
  const channel = new BroadcastChannel('psyevo-private-change')
  channel.postMessage({ ...change, origin: privateChangeOrigin })
  channel.close()
}

const deletionSchema = z.object({
  deletion_id: z.string(),
  target: z.string(),
  version: z.number(),
  status: z.string(),
  completed_steps: z.array(z.string()),
  remaining_steps: z.array(z.string()),
  retryable: z.boolean(),
  external_provider_status: z.enum(['unknown', 'not_applicable']),
})

type SessionItem = z.infer<typeof sessionSchema>

const sessionListSchema = z.object({
  items: z.array(sessionSchema),
  next_cursor: z.string().nullable(),
  has_pending_titles: z.boolean(),
})

function useFinishSessionDeletion() {
  const client = useQueryClient()
  const navigate = useNavigate()
  return async (sessionId: string, current: boolean) => {
    const sessionQueries = {
      predicate: ({ queryKey }: { queryKey: readonly unknown[] }) =>
        ['session', 'current-run', 'history', 'timeline'].includes(
          String(queryKey[0]),
        ) && queryKey[1] === sessionId,
    }
    await Promise.all([
      client.cancelQueries(sessionQueries),
      client.cancelQueries({ queryKey: ['sessions'] }),
    ])
    client.setQueriesData<z.infer<typeof sessionListSchema>>(
      { queryKey: ['sessions'] },
      (data) =>
        data && {
          ...data,
          items: data.items.filter((item) => item.id !== sessionId),
        },
    )
    if (current) await navigate({ to: '/chat', replace: true })
    client.removeQueries(sessionQueries)
    notifyPrivateChange({ type: 'session-deleted', sessionId })
    await Promise.all([
      client.invalidateQueries({ queryKey: ['sessions'] }),
      client.invalidateQueries({ queryKey: ['deletions'] }),
    ])
  }
}

function SessionDeleteDialog({
  session,
  csrf,
  current,
  onBlocking,
  onOpenChange,
  children,
}: {
  session: SessionItem
  csrf: string
  current: boolean
  onBlocking: () => void
  onOpenChange?: (open: boolean) => void
  children: ReactNode
}) {
  const finishDeletion = useFinishSessionDeletion()
  const [open, setOpen] = useState(false)
  const preview = useQuery({
    queryKey: ['deletion-preview', session.id],
    enabled: open,
    staleTime: 0,
    queryFn: ({ signal }) =>
      request(
        `/sessions/${session.id}/deletion-preview`,
        z.object({
          linked_notes: z.array(
            z.object({ id: z.string(), title: z.string() }),
          ),
        }),
        { signal },
      ),
  })
  const changeOpen = (value: boolean) => {
    setOpen(value)
    onOpenChange?.(value)
  }
  const key = useRef(crypto.randomUUID())
  const remove = useMutation({
    mutationFn: async () => {
      onBlocking()
      await request('/sessions/' + session.id, deletionSchema, {
        method: 'DELETE',
        csrf,
        key: key.current,
        body: { expected_version: session.version, confirmed: true },
      })
      await finishDeletion(session.id, current)
      changeOpen(false)
    },
  })
  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent
        className="confirm-dialog"
        onEscapeKeyDown={(event) => {
          if (remove.isPending) event.preventDefault()
        }}
        onInteractOutside={(event) => event.preventDefault()}
      >
        <DialogTitle className="text-base font-semibold">
          确认删除此会话？
        </DialogTitle>
        <DialogDescription className="mt-3 text-sm leading-6">
          将立即停止相关运行并阻断访问，清理消息、历史分支、事件及关联反馈。删除后无法恢复。
        </DialogDescription>
        <p className="mt-2 text-sm text-muted">
          完成情况可在“设置 → 数据管理 → 删除处理记录”中查询。
        </p>
        {preview.isPending || preview.isFetching ? (
          <p role="status">正在核对关联摘记…</p>
        ) : preview.isError ? (
          <p role="alert">暂时无法核对关联摘记，请稍后重试。</p>
        ) : (
          <p className="mt-2 text-sm">
            一并删除的关联摘记：
            {preview.data.linked_notes.map((note) => note.title).join('、') ||
              '无'}
          </p>
        )}
        {remove.isError ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            删除状态尚未确认。请重试原请求，或在设置的数据管理中查询删除处理记录。
          </p>
        ) : null}
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button disabled={remove.isPending}>暂不删除</Button>
          </DialogClose>
          <Button
            className="btn-danger"
            disabled={
              remove.isPending ||
              (!remove.isError &&
                (preview.isPending || preview.isFetching || preview.isError))
            }
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? '正在处理…' : '确认删除'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function SessionList({
  csrf = '',
  currentSessionId,
  onSelect,
  onBlocking,
}: {
  csrf?: string
  currentSessionId?: string
  onSelect?: () => void
  onBlocking: (sessionId: string) => void
}) {
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
        sessionListSchema,
        { signal },
      ),
    refetchInterval: (query) =>
      !query.state.error &&
      query.state.dataUpdateCount < 180 &&
      query.state.data?.has_pending_titles
        ? 2000
        : false,
  })
  return (
    <section
      className="session-browser flex min-h-0 flex-1 flex-col"
      aria-label="我的对话"
    >
      <h2 className="sr-only">我的对话</h2>
      <div className="mb-3 flex items-center gap-2">
        <form
          className="min-w-0 flex-1"
          onSubmit={(e) => {
            e.preventDefault()
            void form.handleSubmit()
          }}
        >
          <form.Field name="search">
            {(field) => (
              <>
                <label htmlFor="sidebar-session-search" className="sr-only">
                  搜索标题
                </label>
                <span className="relative block">
                  <Search
                    size={15}
                    aria-hidden="true"
                    className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
                  />
                  <input
                    id="sidebar-session-search"
                    className="field min-h-9 rounded-lg pr-8 pl-9 text-[13px]"
                    maxLength={120}
                    placeholder="搜索对话…"
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onKeyDown={(e) => {
                      if (
                        e.key === 'Enter' &&
                        field.state.value.trim() === search
                      )
                        void form.handleSubmit()
                    }}
                  />
                  {field.state.value ? (
                    <button
                      type="button"
                      aria-label="清除搜索"
                      className="absolute top-1/2 right-1.5 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-md text-muted transition hover:bg-ink/5 hover:text-ink"
                      onClick={() => {
                        field.handleChange('')
                        setSearch('')
                        setCursor(null)
                      }}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  ) : null}
                </span>
              </>
            )}
          </form.Field>
        </form>
        <label htmlFor="sidebar-session-status" className="sr-only">
          会话范围
        </label>
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value)
            setCursor(null)
          }}
        >
          <SelectTrigger
            id="sidebar-session-status"
            aria-label="会话范围"
            className="min-w-[88px] px-2.5 text-xs"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent align="end">
            <SelectItem value="active">未归档</SelectItem>
            <SelectItem value="archived">已归档</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {list.isPending ? (
        <p className="px-1 text-sm text-muted">正在读取…</p>
      ) : null}
      {list.isError ? (
        <p role="alert" className="px-1 text-sm text-danger">
          列表未能读取。
          <button
            className="btn-ghost ml-1"
            onClick={() => void list.refetch()}
          >
            重试列表
          </button>
        </p>
      ) : null}
      {!list.isError && list.data?.items.length === 0 ? (
        <div className="grid justify-items-center gap-1.5 px-2 py-8 text-center">
          <Inbox size={26} aria-hidden="true" className="text-muted/50" />
          <p className="text-sm text-muted">没有匹配的对话。</p>
          {search ? (
            <button
              className="btn-ghost text-xs"
              onClick={() => {
                setSearch('')
                setCursor(null)
                form.setFieldValue('search', '')
              }}
            >
              清除搜索条件
            </button>
          ) : (
            <p className="text-xs text-muted/70">从上方「新建对话」开始</p>
          )}
        </div>
      ) : null}
      <ul className="session-list -mx-1 flex flex-col gap-1">
        {!list.isError
          ? list.data?.items.map((item) => {
              const title = preferences.data?.display_preferences.hide_titles
                ? '对话'
                : item.title
              return (
                <li
                  key={item.id}
                  className="group/item relative [contain-intrinsic-size:auto_38px] [content-visibility:auto]"
                >
                  <Link
                    to="/chat/$sessionId"
                    params={{ sessionId: item.id }}
                    onClick={onSelect}
                    className="relative flex min-h-[38px] items-center rounded-lg border border-transparent px-3 py-2 pr-9 text-[13.5px] leading-5 text-ink no-underline transition-colors duration-150 hover:bg-ink/5 aria-[current=page]:border-line aria-[current=page]:bg-white aria-[current=page]:font-medium aria-[current=page]:text-accent-strong aria-[current=page]:shadow-sm"
                    activeProps={{ 'aria-current': 'page' }}
                  >
                    <span className="truncate">{title}</span>
                    <span
                      aria-hidden="true"
                      className="absolute top-1/2 left-0 hidden h-4 w-[3px] -translate-y-1/2 rounded-full bg-accent-strong group-aria-current/item:block"
                    />
                  </Link>
                  <small className="hidden">
                    {item.status === 'archived' ? '已归档' : '未归档'}
                  </small>
                  {csrf ? (
                    <SessionDeleteDialog
                      session={item}
                      csrf={csrf}
                      current={item.id === currentSessionId}
                      onBlocking={() => onBlocking(item.id)}
                    >
                      <Button
                        type="button"
                        aria-label={`删除会话：${title}`}
                        className="absolute top-1/2 right-1.5 grid h-7 min-h-0 w-7 -translate-y-1/2 place-items-center rounded-md border-0 bg-transparent p-0 text-muted opacity-0 transition group-focus-within/item:opacity-100 group-hover/item:opacity-100 hover:bg-danger/10 hover:text-danger focus-visible:opacity-100"
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </Button>
                    </SessionDeleteDialog>
                  ) : null}
                </li>
              )
            })
          : null}
      </ul>
      <div className="mt-2 flex flex-wrap gap-2">
        {cursor ? (
          <button className="btn-ghost text-xs" onClick={() => setCursor(null)}>
            返回首批
          </button>
        ) : null}
        {list.data?.next_cursor ? (
          <button
            className="btn-ghost text-xs"
            onClick={() => setCursor(list.data!.next_cursor)}
          >
            下一批对话
          </button>
        ) : null}
      </div>
    </section>
  )
}

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
    <details className="history-panel rounded-xl border border-line bg-paper/50 p-4">
      <summary className="text-sm font-semibold">删除处理记录</summary>
      {jobs.isError ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          删除状态读取失败。
          <button className="btn ml-2" onClick={() => void jobs.refetch()}>
            查询删除状态
          </button>
        </p>
      ) : null}
      {retry.isError ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          清理重试未确认，请查询状态。
        </p>
      ) : null}
      {!jobs.isError && !jobs.data?.items.length ? (
        <p className="mt-3 text-sm text-muted">暂无删除记录。</p>
      ) : null}
      {!jobs.isError
        ? jobs.data?.items.map((job) => (
            <article
              key={job.deletion_id}
              className="deletion-receipt mt-4 grid gap-2 border-t border-line pt-4 text-sm"
            >
              <p className="font-medium">
                {job.status === 'completed'
                  ? '本应用在线内容清理完成'
                  : '已阻断访问，清理尚未完成'}
              </p>
              <p className="text-xs text-muted">回执：{job.deletion_id}</p>
              {job.external_provider_status === 'unknown' ? (
                <p className="text-danger">
                  模型服务商的数据保留及删除状态未知，本回执仅确认本应用在线清理。
                </p>
              ) : null}
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
              <p className="text-xs text-muted">
                本次处理本应用保存的在线内容，保留无正文的删除标记和用量记录。已自行复制的内容不在此范围内。
              </p>
              {job.status !== 'completed' ? (
                <button
                  className="btn justify-self-start"
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
  const [deleteOpen, setDeleteOpen] = useState(false)
  const menu = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const dismiss = (event: PointerEvent | KeyboardEvent) => {
      if (event.defaultPrevented || !menu.current?.open || deleteOpen) return
      if (event instanceof KeyboardEvent) {
        if (event.key !== 'Escape') return
        menu.current.open = false
        menu.current.querySelector('summary')?.focus({ preventScroll: true })
      } else if (
        event.target instanceof Node &&
        !menu.current.contains(event.target)
      ) {
        menu.current.open = false
      }
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', dismiss)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', dismiss)
    }
  }, [deleteOpen])
  const renameRevision = useRef<number | null>(null)
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
          ? {
              title: z.string().trim().min(1).max(120).parse(patch.title),
              expected_title_revision:
                renameRevision.current ?? session.title_revision,
            }
          : {}),
        expected_version: session.version,
      }
      await request('/sessions/' + session.id, sessionSchema, {
        method: 'PATCH',
        csrf,
        body,
      })
      await client.invalidateQueries()
      renameRevision.current = null
      rename.reset()
      notifyPrivateChange({ type: 'session-updated', sessionId: session.id })
    },
    onError: async () => {
      await client.invalidateQueries({ queryKey: ['session', session.id] })
      renameRevision.current = null
    },
  })
  return (
    <section className="session-actions" aria-label="会话管理">
      <details ref={menu} name="conversation-tools" className="group">
        <summary className="btn-ghost inline-flex group-open:bg-paper">
          管理此对话
          <ChevronDown
            size={15}
            aria-hidden="true"
            className="transition-transform group-open:rotate-180"
          />
        </summary>
        <div className="absolute top-full right-3 z-20 mt-1 max-h-[55dvh] w-[min(420px,calc(100%-24px))] overflow-y-auto rounded-xl border border-line bg-white p-4 shadow-xl side:right-5">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              void rename.handleSubmit()
            }}
          >
            <rename.Field name="title">
              {(field) => (
                <label className="w-full text-xs font-medium text-muted">
                  对话标题
                  <input
                    className="field mt-1"
                    maxLength={120}
                    value={field.state.value}
                    onChange={(e) => {
                      renameRevision.current ??= session.title_revision
                      field.handleChange(e.target.value)
                    }}
                  />
                </label>
              )}
            </rename.Field>
            <button className="btn" disabled={active || change.isPending}>
              保存标题
            </button>
            <button
              type="button"
              className="btn"
              disabled={active || change.isPending}
              onClick={() =>
                change.mutate({
                  status: session.status === 'archived' ? 'active' : 'archived',
                })
              }
            >
              {session.status === 'archived' ? '恢复归档' : '归档对话'}
            </button>
            <SessionDeleteDialog
              session={session}
              csrf={csrf}
              current
              onBlocking={onBlocking}
              onOpenChange={setDeleteOpen}
            >
              <Button className="btn-danger">删除会话</Button>
            </SessionDeleteDialog>
          </form>
          {change.isError ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              修改未保存。运行未结束或版本已变化，请查询状态后重试。
            </p>
          ) : null}
          {change.isSuccess ? (
            <p className="mt-3 text-sm text-muted">会话信息已保存。</p>
          ) : null}
        </div>
      </details>
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
    queryKey: ['history', sessionId, 'old-versions', currentId, cursor],
    queryFn: ({ signal }) =>
      request(
        `/sessions/${sessionId}/history?` +
          new URLSearchParams({
            old_only: 'true',
            ...(cursor ? { cursor } : {}),
          }),
        z.object({
          items: z.array(runSchema),
          next_cursor: z.string().nullable(),
        }),
        { signal },
      ),
  })
  if (!cursor && !history.data?.items.length && !history.data?.next_cursor)
    return null
  return (
    <details
      name="conversation-tools"
      className="history-panel old-versions-menu group"
    >
      <summary className="btn-ghost inline-flex text-sm">查看旧版本</summary>
      <div className="old-versions-content absolute right-0 top-full z-20 max-h-[55dvh] w-[min(480px,100%)] overflow-y-auto rounded-xl border border-line bg-white p-4 text-sm shadow-xl">
        {history.isError ? (
          <p role="alert" className="text-danger">
            历史暂不可用。
            <button className="btn ml-2" onClick={() => void history.refetch()}>
              重试历史
            </button>
          </p>
        ) : null}
        {!history.isError
          ? history.data?.items
              .filter((item) => item.is_current === false)
              .map((item) => (
                <article
                  className="history-turn border-b border-line py-3 last:border-b-0"
                  key={item.run_id}
                >
                  <p className="text-xs text-muted">
                    旧分支 · 不用于当前回答 · 输入版本{' '}
                    {item.input_version ?? '—'}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">{item.input_text}</p>
                  {item.output ? (
                    <div className="mt-2 text-muted">
                      <MarkdownMessage text={item.output.text} />
                    </div>
                  ) : null}
                </article>
              ))
          : null}
        <div className="mt-2 flex flex-wrap gap-2">
          {cursor ? (
            <button
              className="btn-ghost text-xs"
              onClick={() => setCursor(null)}
            >
              最新历史
            </button>
          ) : null}
          {history.data?.next_cursor ? (
            <button
              className="btn-ghost text-xs"
              onClick={() => setCursor(history.data!.next_cursor)}
            >
              更早历史
            </button>
          ) : null}
        </div>
      </div>
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
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  const feedbackId = useId()
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="feedback-panel w-full rounded-xl border border-line bg-paper/50 p-4"
    >
      <CollapsibleTrigger ref={trigger}>反馈或纠正 · 可跳过</CollapsibleTrigger>
      <CollapsibleContent forceMount>
        <p className="mt-3 text-xs text-muted">
          用于支持质量反馈和内部评测；不自动附上整段对话，也不会修改你的交流偏好。可不评价或取消。
        </p>
        {save.data ? (
          <p role="status" className="mt-3 text-sm text-muted">
            反馈已保存，回执：{save.data.feedback_id}
          </p>
        ) : (
          <form
            className="mt-3 grid gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              void form.handleSubmit()
            }}
          >
            <form.Field name="helpfulness">
              {(field) => (
                <div className="text-xs font-medium text-muted">
                  <label htmlFor={`${feedbackId}-helpfulness`}>这次回答</label>
                  <Select
                    value={field.state.value}
                    onValueChange={field.handleChange}
                  >
                    <SelectTrigger
                      id={`${feedbackId}-helpfulness`}
                      className="mt-1 flex min-h-10 w-full max-w-xs"
                      onBlur={field.handleBlur}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="not_rated">不评价</SelectItem>
                      <SelectItem value="helpful">有帮助</SelectItem>
                      <SelectItem value="neutral">一般</SelectItem>
                      <SelectItem value="unhelpful">不合适</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </form.Field>
            <form.Field name="category">
              {(field) => (
                <div className="text-xs font-medium text-muted">
                  <label htmlFor={`${feedbackId}-category`}>反馈类型</label>
                  <Select
                    value={field.state.value}
                    onValueChange={field.handleChange}
                  >
                    <SelectTrigger
                      id={`${feedbackId}-category`}
                      className="mt-1 flex min-h-10 w-full max-w-xs"
                      onBlur={field.handleBlur}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="general">一般反馈</SelectItem>
                      <SelectItem value="misunderstood">
                        这里误解了我
                      </SelectItem>
                      <SelectItem value="listen_only">我只想倾听</SelectItem>
                      <SelectItem value="inappropriate">回答不合适</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </form.Field>
            <form.Field name="comment">
              {(field) => (
                <label className="text-xs font-medium text-muted">
                  补充说明（可选）
                  <Textarea
                    className="mt-1"
                    rows={3}
                    maxLength={1000}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onBlur={field.handleBlur}
                  />
                </label>
              )}
            </form.Field>
            {save.isError ? (
              <p role="alert" className="text-sm text-danger">
                反馈未确认，未显示已保存。重试原反馈不会重复提交。
              </p>
            ) : null}
            <div className="flex gap-3">
              <Button
                type="submit"
                className="btn-primary"
                disabled={save.isPending}
              >
                提交反馈
              </Button>
              <Button
                type="button"
                disabled={save.isPending}
                onClick={() => {
                  form.reset()
                  save.reset()
                  pending.current = null
                  setOpen(false)
                  trigger.current?.focus()
                }}
              >
                取消反馈
              </Button>
            </div>
          </form>
        )}
      </CollapsibleContent>
    </Collapsible>
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
  const [revisionOpen, setRevisionOpen] = useState(false)
  const revisionButton = useRef<HTMLButtonElement>(null)
  const closeRevision = () => {
    setRevisionOpen(false)
    revisionButton.current?.focus({ preventScroll: true })
  }
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
    },
    onSettled: async () => {
      // A revision draft may have persisted even when its start acknowledgement failed.
      await client.invalidateQueries({ queryKey: ['current-run', sessionId] })
      await client.invalidateQueries({ queryKey: ['history', sessionId] })
      await client.invalidateQueries({ queryKey: ['timeline', sessionId] })
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
    <div className="branch-actions order-[-1] flex w-full flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      {run.status === 'draft' ? (
        <button
          className="btn"
          disabled={mutate.isPending}
          onClick={() => mutate.mutate({ kind: 'start' })}
        >
          生成本分支回答
        </button>
      ) : (
        <Collapsible
          open={revisionOpen}
          onOpenChange={setRevisionOpen}
          className="contents"
        >
          <button
            className="regenerate-button btn-ghost -ml-2 inline-flex"
            disabled={mutate.isPending}
            onClick={() => mutate.mutate({ kind: 'regenerate' })}
          >
            <RotateCcw size={15} aria-hidden="true" />
            {mutate.isPending ? '正在提交…' : '重新生成'}
          </button>
          <CollapsibleTrigger
            ref={revisionButton}
            className="btn-ghost inline-flex w-auto! aria-expanded:bg-paper"
          >
            修订最后输入
          </CollapsibleTrigger>
          <CollapsibleContent
            forceMount
            className="mt-2 min-w-0 basis-full rounded-xl border border-line bg-paper/50 p-4"
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.stopPropagation()
                closeRevision()
              }
            }}
          >
            <p className="text-xs text-muted">
              运行结束后才能修订。新版本生成新回答，旧版本保留在历史中。
            </p>
            <form
              className="mt-3 grid gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                void form.handleSubmit()
              }}
            >
              <form.Field name="content">
                {(field) => (
                  <label className="text-xs font-medium text-muted">
                    修订内容
                    <Textarea
                      className="field mt-1 resize-y"
                      maxLength={4000}
                      rows={4}
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </label>
                )}
              </form.Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  className="btn-primary"
                  disabled={mutate.isPending}
                >
                  保存修订并生成
                </Button>
                <Button
                  type="button"
                  className="btn-ghost"
                  onClick={closeRevision}
                >
                  收起修订
                </Button>
              </div>
            </form>
          </CollapsibleContent>
        </Collapsible>
      )}
      {mutate.isError ? (
        <p role="alert" className="basis-full text-sm text-danger">
          操作未确认，保留原输入。请重试原操作；活动运行不能修订。
        </p>
      ) : null}
    </div>
  )
}
