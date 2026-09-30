import { useForm } from '@tanstack/react-form'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { Link, useBlocker, useNavigate } from '@tanstack/react-router'
import { BookOpen, Moon, Plus } from 'lucide-react'
import { useRef, useState } from 'react'
import { z } from 'zod'
import { getIdentity, request, RequestError } from './account-api'
import { Button } from './components/ui/button'
import { Input } from './components/ui/input'
import { Textarea } from './components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from './components/ui/dialog'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from './components/ui/select'
import {
  cardSchema,
  noteSchema,
  sleepSchema,
  recordPaths,
  type Note,
  type Sleep,
  type Card,
  type RecordKind,
} from './records-api'
import { sessionSchema } from './support-api'
import { notifyPrivateChange } from './history-page'

const tabClass =
  'inline-flex items-center gap-2 border-b-2 border-transparent px-4 py-3 text-sm text-muted aria-[current=page]:border-ink aria-[current=page]:text-ink'
const labels: Record<string, string> = {
  title: '标题（可选）',
  body: '正文',
  annotation: '批注（可选）',
  occurred_at: '发生时间（可选，含时区偏移）',
  timezone: '时区（如 Asia/Shanghai）',
  tags: '标签（可选，用逗号分隔）',
  entry_date: '记录日期',
  bed_at: '入睡时间（可选，含时区偏移）',
  wake_at: '起床时间（可选，含时区偏移）',
  interruptions: '中断次数（可选）',
  feeling: '主观感受（可选）',
  note: '备注（可选）',
  helpful_methods: '对我有帮助的方法',
  self_reminders: '想提醒自己的话',
  contact_notes: '愿意主动联系的人或渠道',
}
const multiline = new Set([
  'body',
  'annotation',
  'note',
  'helpful_methods',
  'self_reminders',
  'contact_notes',
])

function valuesFor(
  kind: RecordKind,
  record?: Note | Sleep | Card,
): Record<string, string> {
  const keys =
    kind === 'note'
      ? [
          'title',
          ...(record && 'kind' in record && record.kind === 'linked_excerpt'
            ? ['annotation']
            : ['body']),
          'occurred_at',
          'timezone',
          'tags',
        ]
      : kind === 'sleep_record'
        ? [
            'entry_date',
            'bed_at',
            'wake_at',
            'timezone',
            'interruptions',
            'feeling',
            'note',
          ]
        : ['helpful_methods', 'self_reminders', 'contact_notes']
  return Object.fromEntries(
    keys.map((key) => {
      const value = record && key in record ? Reflect.get(record, key) : ''
      return [
        key,
        Array.isArray(value)
          ? value.join(', ')
          : value == null
            ? ''
            : String(value),
      ]
    }),
  )
}

export function RecordsPage({ sleep = false }: { sleep?: boolean }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(false)
  const editorOpen = creating || editing
  const [q, setQ] = useState('')
  const [day, setDay] = useState('')
  const [kind, setKind] = useState('all')
  const filter = useForm({
    defaultValues: { q: '', day: '' },
    onSubmit: ({ value }) => {
      if (editorOpen) return
      setQ(value.q)
      setDay(value.day)
      setSelected(null)
    },
  })
  const path = sleep ? '/sleep-records' : '/notes'
  const list = useInfiniteQuery({
    queryKey: ['records', path, q, day, kind],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      request(
        path +
          '?' +
          new URLSearchParams({
            ...(q ? { q } : {}),
            ...(day ? { date: day } : {}),
            ...(!sleep && kind !== 'all' ? { type: kind } : {}),
            ...(pageParam ? { cursor: pageParam } : {}),
          }),
        z.object({
          items: z.array(z.union([noteSchema, sleepSchema])),
          next_cursor: z.string().nullable(),
        }),
        { signal },
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  const detail = useQuery({
    queryKey: ['record', path, selected],
    enabled: !!selected,
    queryFn: ({ signal }) =>
      request(`${path}/${selected}`, z.union([noteSchema, sleepSchema]), {
        signal,
      }),
  })
  return (
    <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-7 page:px-8">
      <header>
        <p className="eyebrow mb-2">留给自己的空间</p>
        <h1 className="text-2xl font-semibold tracking-tight">我的记录</h1>
        <p className="mt-2 text-sm text-muted">
          记下经历，也给自己一点整理的时间。
        </p>
      </header>
      <nav aria-label="记录类型" className="mt-5 flex border-b border-line">
        <Link
          to="/records"
          className={tabClass}
          activeOptions={{ exact: true }}
          activeProps={{ 'aria-current': 'page' }}
        >
          <BookOpen size={16} />
          笔记
        </Link>
        <Link
          to="/records/sleep"
          className={tabClass}
          activeProps={{ 'aria-current': 'page' }}
        >
          <Moon size={16} />
          睡眠
        </Link>
      </nav>
      <form
        className="my-5 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          void filter.handleSubmit()
        }}
      >
        {!sleep ? (
          <label className="grid gap-1 text-xs text-muted">
            类型
            <Select
              disabled={editorOpen}
              value={kind}
              onValueChange={(value) => {
                setKind(value)
                setSelected(null)
              }}
            >
              <SelectTrigger aria-label="笔记类型" className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部笔记</SelectItem>
                <SelectItem value="free">自由笔记</SelectItem>
                <SelectItem value="linked_excerpt">消息摘记</SelectItem>
              </SelectContent>
            </Select>
          </label>
        ) : null}
        <filter.Field name="day">
          {(field) => (
            <label className="grid gap-1 text-xs text-muted">
              日期
              <Input
                type="date"
                value={field.state.value}
                onChange={(event) => field.handleChange(event.target.value)}
              />
            </label>
          )}
        </filter.Field>
        {!sleep ? (
          <filter.Field name="q">
            {(field) => (
              <label className="grid min-w-40 flex-1 gap-1 text-xs text-muted">
                关键词
                <Input
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                  placeholder="搜索自己的记录"
                />
              </label>
            )}
          </filter.Field>
        ) : null}
        <Button type="submit" disabled={editorOpen}>
          筛选
        </Button>
        <Button
          className="btn-primary ml-auto"
          disabled={editorOpen}
          onClick={() => {
            setSelected(null)
            setCreating(true)
          }}
        >
          <Plus size={16} />
          {sleep ? '记录睡眠' : '新建笔记'}
        </Button>
      </form>
      <div className="grid min-h-80 flex-1 gap-6 page:grid-cols-[260px_minmax(0,1fr)]">
        <aside
          aria-label="记录列表"
          className={`${selected || creating ? 'hidden page:block' : ''} border-line page:border-r page:pr-5`}
        >
          {list.isError ? (
            <p role="alert">
              暂时无法读取记录。
              <Button onClick={() => void list.refetch()}>重试</Button>
            </p>
          ) : list.isPending ? (
            <p role="status">正在读取…</p>
          ) : !list.data.pages[0]?.items.length ? (
            <p className="py-8 text-sm text-muted">
              还没有记录。可以从一件小事开始。
            </p>
          ) : (
            list.data.pages
              .flatMap((page) => page.items)
              .map((item) => (
                <Button
                  key={item.id}
                  disabled={editorOpen}
                  aria-pressed={selected === item.id}
                  className="mb-2 block w-full rounded-xl px-4 py-4 text-left aria-pressed:bg-accent"
                  onClick={() => {
                    setCreating(false)
                    setSelected(item.id)
                  }}
                >
                  <span className="block truncate font-medium">
                    {'title' in item
                      ? item.title || '未命名笔记'
                      : item.entry_date}
                  </span>
                  <span className="mt-1 block text-xs text-muted">
                    {'status' in item
                      ? {
                          draft: '草稿',
                          saved: '已保存',
                          needs_review: '来源已变化 · 需核对',
                          deleted: '已删除',
                        }[item.status]
                      : item.feeling || '感受未填写'}
                  </span>
                </Button>
              ))
          )}
          {list.hasNextPage ? (
            <Button
              disabled={list.isFetchingNextPage}
              onClick={() => void list.fetchNextPage()}
            >
              加载更多
            </Button>
          ) : null}
        </aside>
        <main className="min-w-0">
          {creating ? (
            <RecordEditor
              key={`new-${path}`}
              kind={sleep ? 'sleep_record' : 'note'}
              onDone={(id) => {
                setCreating(false)
                setSelected(id)
              }}
              onCancel={() => setCreating(false)}
            />
          ) : selected ? (
            detail.isError ? (
              <p role="alert">
                记录不可用或已删除。
                <Button onClick={() => setSelected(null)}>返回列表</Button>
              </p>
            ) : detail.data ? (
              <RecordDetail
                key={selected}
                kind={sleep ? 'sleep_record' : 'note'}
                record={detail.data}
                onEditing={setEditing}
                onBack={() => setSelected(null)}
              />
            ) : (
              <p role="status">正在读取详情…</p>
            )
          ) : (
            <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-line p-8 text-center">
              <BookOpen className="mb-4 text-muted" size={28} />
              <p className="font-medium">选择一条记录，慢慢看</p>
              <p className="mt-2 text-sm text-muted">
                内容保存在你的账号中，只有你可以查看。
              </p>
            </div>
          )}
        </main>
      </div>
    </section>
  )
}

function RecordDetail({
  kind,
  record,
  onBack,
  onEditing,
}: {
  kind: RecordKind
  record: Note | Sleep
  onBack: () => void
  onEditing: (editing: boolean) => void
}) {
  const [editing, setEditing] = useState(false)
  if (editing)
    return (
      <RecordEditor
        kind={kind}
        record={record}
        onCancel={() => {
          setEditing(false)
          onEditing(false)
        }}
        onDone={() => {
          setEditing(false)
          onEditing(false)
        }}
      />
    )
  return (
    <article className="px-1 py-2">
      <Button className="btn-ghost mb-4 page:hidden" onClick={onBack}>
        返回列表
      </Button>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-xl font-semibold">
          {'title' in record ? record.title || '未命名笔记' : record.entry_date}
        </h2>
        <Button
          onClick={() => {
            setEditing(true)
            onEditing(true)
          }}
        >
          编辑
        </Button>
        <DeleteRecord kind={kind} record={record} onDone={onBack} />
        <BringRecord
          kind={kind}
          record={record}
          disabled={'status' in record && record.status !== 'saved'}
        />
      </div>
      <p className="mt-3 text-xs text-muted">
        仅自己可见 · 版本 {record.version}
      </p>
      {'body' in record ? (
        <>
          <p className="my-6 leading-8 whitespace-pre-wrap wrap-anywhere">
            {record.body}
          </p>
          {record.status === 'needs_review' ? (
            <p role="status" className="rounded-xl bg-paper p-4">
              来源已修订或不可用，请核对；此摘记暂不能带入对话。
            </p>
          ) : (
            record.source_messages.map((message) => (
              <blockquote
                key={message.id}
                className="my-4 border-l-2 border-line pl-4 leading-8 whitespace-pre-wrap"
              >
                {message.content}
              </blockquote>
            ))
          )}
          {record.annotation ? (
            <p className="mt-5 whitespace-pre-wrap">
              批注：{record.annotation}
            </p>
          ) : null}
          <p className="mt-6 text-xs text-muted">{record.tags.join(' · ')}</p>
        </>
      ) : (
        <dl className="my-8 grid grid-cols-[auto_1fr] gap-x-6 gap-y-4 text-sm">
          {Object.entries({
            入睡时间: record.bed_at || '未填写',
            起床时间: record.wake_at || '未填写',
            时区: record.timezone || '未填写',
            中断次数: record.interruptions ?? '未知',
            主观感受: record.feeling || '未填写',
            备注: record.note || '未填写',
            记录的时间跨度:
              record.span_minutes == null
                ? '起止不完整，暂不计算'
                : `${record.span_minutes} 分钟（不是实际睡眠时长）`,
          }).map(([key, value]) => (
            <div className="contents" key={key}>
              <dt className="text-muted">{key}</dt>
              <dd className="whitespace-pre-wrap wrap-anywhere">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </article>
  )
}

export function RecordEditor({
  kind,
  record: inputRecord,
  onDone,
  onCancel,
}: {
  kind: RecordKind
  record?: Note | Sleep | Card
  onDone: (id: string) => void
  onCancel?: () => void
}) {
  const [record] = useState(inputRecord)
  const [recordId, setRecordId] = useState(record?.id)
  const [baseVersion, setBaseVersion] = useState(record?.version ?? 0)
  const [latest, setLatest] = useState<Note | Sleep | Card | null>(null)
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
  const client = useQueryClient()
  const [initial] = useState(() => valuesFor(kind, record))
  const [dirty, setDirty] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [status, setStatus] = useState(
    record && 'status' in record && record.status === 'draft'
      ? 'draft'
      : 'saved',
  )
  const [saved, setSaved] = useState('')
  const [error, setError] = useState('')
  const statusRef = useRef(status)
  const pending = useRef<{
    key: string
    body: unknown
    values: Record<string, string>
    status: string
    baseVersion: number
  } | null>(null)
  const blocker = useBlocker({
    shouldBlockFn: () => dirty,
    withResolver: true,
    enableBeforeUnload: dirty,
  })
  const save = useMutation({
    mutationFn: async (values: Record<string, string>) => {
      setError('')
      setSaved('')
      const nullable = (key: string) => values[key]?.trim() || null
      const textValues = z
        .record(z.string(), z.string().max(20000))
        .parse(values)
      let body: Record<string, unknown>
      if (kind === 'note') {
        const linked =
          record && 'kind' in record && record.kind === 'linked_excerpt'
        if (!linked && !textValues.body.trim()) throw new Error('请填写正文。')
        body = {
          kind: linked ? 'linked_excerpt' : 'free',
          title: values.title,
          body: linked ? null : values.body,
          annotation: values.annotation || '',
          occurred_at: nullable('occurred_at'),
          timezone: nullable('timezone'),
          tags: values.tags
            .split(/[,，]/)
            .map((v) => v.trim())
            .filter(Boolean),
          status,
          source_refs: linked ? record.source_refs : [],
        }
      } else if (kind === 'sleep_record') {
        z.iso.date().parse(values.entry_date)
        body = {
          entry_date: values.entry_date,
          bed_at: nullable('bed_at'),
          wake_at: nullable('wake_at'),
          timezone: nullable('timezone'),
          interruptions:
            nullable('interruptions') == null
              ? null
              : Number(values.interruptions),
          feeling: values.feeling,
          note: values.note,
        }
      } else body = { ...values, resource_refs: [] }
      if (recordId || kind === 'support_card')
        body.expected_version = baseVersion
      if (
        pending.current &&
        JSON.stringify(pending.current.body) !== JSON.stringify(body)
      )
        throw new Error(
          '上次保存结果尚未确认，请先核对原请求。编辑内容已保留。',
        )
      pending.current ??= {
        key: crypto.randomUUID(),
        body,
        values: { ...values },
        status,
        baseVersion,
      }
      const submitted = pending.current
      const path =
        recordPaths[kind] +
        (recordId && kind !== 'support_card' ? `/${recordId}` : '')
      try {
        const value = await request(
          path,
          z.union([noteSchema, sleepSchema, cardSchema]),
          {
            method:
              kind === 'support_card' ? 'PUT' : recordId ? 'PATCH' : 'POST',
            body,
            key: submitted.key,
            csrf: identity.data?.csrf_token,
            signal: AbortSignal.timeout(15000),
          },
        )
        if (value.id) await finishSave(value.id, submitted)
      } catch (cause) {
        if (cause instanceof RequestError && cause.status < 500)
          pending.current = null
        if (cause instanceof RequestError && cause.status === 409) {
          const current = await request(
            path,
            z.union([noteSchema, sleepSchema, cardSchema]),
          ).catch(() => null)
          setLatest(current)
        }
        throw cause
      }
    },
    onError: (cause) =>
      setError(
        cause instanceof RequestError && cause.status === 409
          ? '版本冲突：另一处已经修改。你的编辑保留在这里，请与最新保存内容核对后重试。'
          : cause instanceof RequestError && cause.status === 422
            ? '请核对字段：日期时间需包含正确的时区偏移，起床必须晚于入睡；来源和正文必须有效。'
            : cause instanceof z.ZodError
              ? '请检查日期与字段格式。'
              : cause instanceof Error
                ? cause.message
                : '保存未确认，编辑内容已保留。',
      ),
  })
  const form = useForm({
    defaultValues: initial,
    onSubmit: async ({ value }) => {
      await save.mutateAsync(value).catch(() => undefined)
    },
  })
  const finishSave = async (
    id: string,
    submitted: NonNullable<typeof pending.current>,
  ) => {
    await client.invalidateQueries({ queryKey: ['records'] })
    await client.invalidateQueries({ queryKey: ['record'] })
    const changed =
      statusRef.current !== submitted.status ||
      Object.entries(submitted.values).some(
        ([key, value]) => form.state.values[key] !== value,
      )
    pending.current = null
    setRecordId(id)
    // Keep the submitted version baseline so concurrent edits still conflict.
    setBaseVersion(submitted.baseVersion + 1)
    setDirty(changed)
    setError('')
    setSaved(
      changed
        ? '原请求已保存；之后的编辑仍未保存，请继续保存。'
        : `已保存 · 版本 ${submitted.baseVersion + 1}`,
    )
    if (!changed) onDone(id)
  }
  const reconcile = useMutation({
    mutationFn: async () => {
      const submitted = pending.current
      if (!submitted) return
      try {
        const receipt = await request(
          `/record-requests/${submitted.key}`,
          z.object({ committed: z.literal(true), resource_id: z.string() }),
        )
        await finishSave(receipt.resource_id, submitted)
      } catch (cause) {
        if (cause instanceof RequestError && cause.status === 404) {
          setError(
            '尚未找到保存收据，可重试原请求；使用同一请求编号，不会重复新建。',
          )
          return
        }
        throw cause
      }
    },
  })
  return (
    <>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault()
          void form.handleSubmit()
        }}
      >
        <h2 className="text-xl font-semibold">
          {kind === 'support_card'
            ? '支持备忘卡'
            : recordId
              ? '编辑记录'
              : kind === 'note'
                ? '写一条笔记'
                : '记录睡眠'}
        </h2>
        {kind === 'support_card' ? (
          <p className="text-sm text-muted">
            全部自愿填写，可只写一项。这里只记录你想留给自己的内容，不会自动联系任何人。
          </p>
        ) : (
          <p className="text-xs leading-6 text-muted">
            时间可留空；填写时使用完整日期和偏移，例如
            2026-09-30T23:10:00+08:00。时区填写 Asia/Shanghai 等 IANA 名称。
          </p>
        )}
        {record && 'source_messages' in record
          ? record.source_messages.map((message) => (
              <blockquote
                key={message.id}
                className="rounded-xl bg-paper p-4 whitespace-pre-wrap"
              >
                {message.content}
              </blockquote>
            ))
          : null}
        {Object.keys(initial).map((key) => (
          <form.Field key={key} name={key}>
            {(field) => (
              <label className="grid gap-2 text-sm font-medium">
                {labels[key]}
                {multiline.has(key) ? (
                  <Textarea
                    aria-label={labels[key]}
                    rows={key === 'body' ? 9 : 4}
                    className="field w-full resize-y font-normal"
                    value={field.state.value}
                    onChange={(event) => {
                      field.handleChange(event.target.value)
                      setDirty(true)
                    }}
                  />
                ) : (
                  <Input
                    aria-label={labels[key]}
                    type={
                      key === 'entry_date'
                        ? 'date'
                        : key === 'interruptions'
                          ? 'number'
                          : 'text'
                    }
                    min={key === 'interruptions' ? 0 : undefined}
                    value={field.state.value}
                    onChange={(event) => {
                      field.handleChange(event.target.value)
                      setDirty(true)
                    }}
                  />
                )}
              </label>
            )}
          </form.Field>
        ))}
        {kind === 'note' ? (
          <label className="grid gap-2 text-sm">
            保存状态
            <Select
              value={status}
              onValueChange={(value) => {
                statusRef.current = value
                setStatus(value)
                setDirty(true)
              }}
            >
              <SelectTrigger aria-label="保存状态">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="saved">已完成</SelectItem>
                <SelectItem value="draft">草稿</SelectItem>
              </SelectContent>
            </Select>
          </label>
        ) : null}
        {kind === 'support_card' ? (
          <p className="text-xs text-muted">
            资源状态：
            {record &&
            'resource_status' in record &&
            record.resource_status === 'needs_review'
              ? '需核对，引用暂不可用'
              : '暂无已核实的公共资源'}
            。个人提醒仍可保存。
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
        {latest ? (
          <div className="rounded-xl border border-line p-4">
            <h3 className="font-medium">
              最新保存内容 · 版本 {latest.version}
            </h3>
            <dl className="mt-3 space-y-2 text-sm">
              {Object.entries(valuesFor(kind, latest)).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-muted">{labels[key]}</dt>
                  <dd className="whitespace-pre-wrap">{value || '未填写'}</dd>
                </div>
              ))}
            </dl>
            <Button
              className="mt-4"
              onClick={() => {
                setBaseVersion(latest.version)
                setLatest(null)
                setError(
                  '已采用最新版本号，你的编辑内容保持不变，请核对后保存。',
                )
              }}
            >
              已核对，保留我的编辑继续
            </Button>
          </div>
        ) : null}
        {saved ? <p role="status">{saved}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            className="btn-primary"
            disabled={save.isPending || reconcile.isPending}
          >
            {save.isPending ? '正在保存…' : '保存'}
          </Button>
          {save.isError ? (
            <Button
              disabled={save.isPending || reconcile.isPending}
              onClick={() => reconcile.mutate()}
            >
              核对保存结果
            </Button>
          ) : null}
          {onCancel ? (
            <Button
              disabled={save.isPending || reconcile.isPending}
              onClick={() => (dirty ? setDiscard(true) : onCancel())}
            >
              返回
            </Button>
          ) : null}
        </div>
        {reconcile.isError ? (
          <p role="alert">暂时无法核对，内容已保留。</p>
        ) : null}
      </form>
      <Dialog
        open={discard || blocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open) {
            setDiscard(false)
            blocker.reset?.()
          }
        }}
      >
        <DialogContent>
          <DialogTitle>放弃未保存的修改？</DialogTitle>
          <DialogDescription className="mt-3">
            编辑内容尚未保存。返回编辑可以继续保存。
          </DialogDescription>
          <div className="mt-5 flex gap-3">
            <Button
              onClick={() => {
                setDiscard(false)
                blocker.reset?.()
              }}
            >
              继续编辑
            </Button>
            <Button
              className="btn-danger"
              onClick={() => {
                setDirty(false)
                setDiscard(false)
                if (blocker.status === 'blocked') blocker.proceed()
                else onCancel?.()
              }}
            >
              放弃修改
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function DeleteRecord({
  kind,
  record,
  onDone,
}: {
  kind: RecordKind
  record: { id: string | null; version: number }
  onDone: () => void
}) {
  const [open, setOpen] = useState(false)
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
  const key = useRef(crypto.randomUUID())
  const client = useQueryClient()
  const remove = useMutation({
    mutationFn: async () => {
      const receipt = await request(
        recordPaths[kind] + (kind === 'support_card' ? '' : `/${record.id}`),
        z.object({ status: z.string() }),
        {
          method: 'DELETE',
          body: { expected_version: record.version, confirmed: true },
          key: key.current,
          csrf: identity.data?.csrf_token,
        },
      )
      await client.cancelQueries({ queryKey: ['record'] })
      client.removeQueries({ queryKey: ['record'] })
      await client.invalidateQueries({ queryKey: ['records'] })
      await client.invalidateQueries({ queryKey: ['deletions'] })
      notifyPrivateChange({ type: 'records-deleted' })
      for (const name of ['timeline', 'history', 'current-run', 'session']) {
        await client.cancelQueries({ queryKey: [name] })
        client.removeQueries({ queryKey: [name] })
      }
      if (receipt.status !== 'completed')
        throw new Error('访问已阻断，清理尚未完成；请在设置的数据管理中重试。')
      setOpen(false)
      onDone()
    },
  })
  return (
    <>
      <Button
        className="btn-danger"
        disabled={!record.id}
        onClick={() => setOpen(true)}
      >
        {kind === 'support_card' ? '清空' : '删除'}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!remove.isPending) setOpen(value)
        }}
      >
        <DialogContent>
          <DialogTitle>
            {kind === 'support_card' ? '确认清空备忘卡？' : '确认删除记录？'}
          </DialogTitle>
          <DialogDescription className="mt-3">
            将删除内容及关联版本，停止相关运行并清理派生回答。此操作无法恢复。
          </DialogDescription>
          {remove.isError ? (
            <p role="alert" className="mt-3 text-danger">
              {remove.error.message}
            </p>
          ) : null}
          <div className="mt-5 flex gap-3">
            <DialogClose asChild>
              <Button disabled={remove.isPending}>暂不删除</Button>
            </DialogClose>
            <Button
              className="btn-danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              确认删除
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function BringRecord({
  kind,
  record,
  disabled,
}: {
  kind: RecordKind
  record: { id: string | null; version: number }
  disabled?: boolean
}) {
  const navigate = useNavigate()
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
  const key = useRef(crypto.randomUUID())
  const bring = useMutation({
    mutationFn: async () => {
      const session = await request('/sessions', sessionSchema, {
        method: 'POST',
        body: {},
        key: key.current,
        csrf: identity.data?.csrf_token,
      })
      await navigate({
        to: '/chat/$sessionId',
        params: { sessionId: session.id },
        search: {
          record: record.id ?? undefined,
          recordType: kind,
          recordVersion: record.version,
        },
      })
    },
  })
  return (
    <>
      <Button
        disabled={disabled || bring.isPending || !record.id}
        onClick={() => bring.mutate()}
      >
        带入本次对话
      </Button>
      {bring.isError ? <p role="alert">暂时无法建立对话，请重试。</p> : null}
    </>
  )
}

export function SupportCardPage() {
  const card = useQuery({
    queryKey: ['record', '/support-card'],
    queryFn: ({ signal }) => request('/support-card', cardSchema, { signal }),
  })
  const [revision, setRevision] = useState(0)
  const [old, setOld] = useState(false)
  return (
    <section className="mx-auto w-full max-w-3xl px-5 py-8">
      <Link
        to="/me"
        search={{ section: 'preferences' }}
        className="text-sm text-muted"
      >
        ← 我的设置
      </Link>
      <div className="mt-6">
        {card.isError ? (
          <p role="alert">
            备忘卡暂不可用。
            <Button onClick={() => void card.refetch()}>重试</Button>
          </p>
        ) : card.data ? (
          <>
            <RecordEditor
              key={revision}
              kind="support_card"
              record={card.data}
              onDone={() => {
                void card.refetch()
                setRevision((value) => value + 1)
              }}
            />
            <div className="mt-5 flex flex-wrap gap-3">
              <Button
                disabled={!card.data.previous_content}
                onClick={() => setOld(true)}
              >
                查看旧版本差异
              </Button>
              <DeleteRecord
                kind="support_card"
                record={card.data}
                onDone={() => {
                  void card.refetch()
                  setRevision((value) => value + 1)
                }}
              />
              <BringRecord kind="support_card" record={card.data} />
            </div>
            <Dialog open={old} onOpenChange={setOld}>
              <DialogContent>
                <DialogTitle>
                  上次保存内容 · 版本 {card.data.previous_content?.version}
                </DialogTitle>
                <DialogDescription>
                  可与当前编辑内容对照核对。
                </DialogDescription>
                {card.data.previous_content
                  ? ['helpful_methods', 'self_reminders', 'contact_notes'].map(
                      (key) => (
                        <div key={key} className="mt-4">
                          <h3 className="text-sm font-medium">{labels[key]}</h3>
                          <p className="mt-2 whitespace-pre-wrap">
                            {String(
                              Reflect.get(card.data!.previous_content!, key),
                            ) || '未填写'}
                          </p>
                        </div>
                      ),
                    )
                  : null}
                <DialogClose asChild>
                  <Button className="mt-5">关闭</Button>
                </DialogClose>
              </DialogContent>
            </Dialog>
          </>
        ) : (
          <p role="status">正在读取…</p>
        )}
      </div>
    </section>
  )
}

export function ExcerptButton({
  messageId,
  version,
  content,
  role = 'user',
}: {
  messageId: string
  version: number
  content: string
  role?: 'user' | 'assistant'
}) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const note: Note = {
    id: '',
    version: 0,
    kind: 'linked_excerpt',
    title: '',
    body: null,
    annotation: '',
    occurred_at: null,
    timezone: null,
    tags: [],
    status: 'saved',
    source_refs: [
      { source_type: 'message', source_id: messageId, source_version: version },
    ],
    source_messages: [{ id: messageId, version, role, content }],
  }
  return (
    <>
      <Button className="btn-ghost mt-1 text-xs" onClick={() => setOpen(true)}>
        加入笔记
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          onInteractOutside={(event) => event.preventDefault()}
          onEscapeKeyDown={(event) => event.preventDefault()}
        >
          <DialogTitle className="sr-only">保存消息摘记</DialogTitle>
          <DialogDescription className="mb-4 text-sm">
            消息以关联引用保存。源修订后需核对，删源时一起删除。
          </DialogDescription>
          <RecordEditor
            kind="note"
            record={note}
            onCancel={() => setOpen(false)}
            onDone={() => {
              setOpen(false)
              void navigate({ to: '/records', ignoreBlocker: true })
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  )
}
