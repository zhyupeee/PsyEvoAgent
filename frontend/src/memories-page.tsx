import { useForm } from '@tanstack/react-form'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { Link, useBlocker } from '@tanstack/react-router'
import { Brain, Pencil, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { z } from 'zod'
import { getIdentity, request, RequestError } from './account-api'
import { Button } from './components/ui/button'
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
import { notifyPrivateChange } from './history-page'

const sourceSchema = z.object({
  source_type: z.string(),
  source_id: z.string(),
  source_version: z.number(),
})
const memorySchema = z.object({
  id: z.string(),
  version: z.number(),
  content: z.string(),
  claim_type: z.enum([
    'user_statement',
    'user_feeling',
    'system_inference',
    'confirmed_preference',
  ]),
  status: z.string(),
  event_time: z.string().nullable(),
  recorded_at: z.string(),
  source_refs: z.array(sourceSchema),
  source_available: z.boolean(),
})
type Memory = z.infer<typeof memorySchema>
const claimNames = {
  user_statement: '你的记录',
  user_feeling: '你描述的感受',
  system_inference: '系统推断 · 可更正',
  confirmed_preference: '你确认的偏好',
}
const sourceNames: Record<string, string> = {
  note: '笔记',
  message: '对话消息',
  sleep_record: '睡眠记录',
  support_card: '支持备忘卡',
}

export function MemoriesPage() {
  const [status, setStatus] = useState('active')
  const statusTrigger = useRef<HTMLButtonElement>(null)
  const [selected, setSelected] = useState<{
    row: Memory
    action: 'edit' | 'forget' | 'stop'
    opener: HTMLButtonElement
  } | null>(null)
  const list = useInfiniteQuery({
    queryKey: ['memories', status],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      request(
        '/memories?' +
          new URLSearchParams({
            status,
            ...(pageParam ? { cursor: pageParam } : {}),
          }),
        z.object({
          items: z.array(memorySchema),
          next_cursor: z.string().nullable(),
        }),
        { signal },
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 5000,
  })
  const items = list.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <section className="mx-auto w-full max-w-4xl px-4 py-8 page:px-8">
      <Link
        to="/me"
        search={{ section: 'models' }}
        className="text-sm text-muted"
      >
        返回设置
      </Link>
      <header className="mt-6 border-b border-line pb-6">
        <Brain size={26} className="mb-4 text-muted" aria-hidden="true" />
        <p className="eyebrow mb-2">可以核对，也可以放下</p>
        <h1 className="text-2xl font-semibold tracking-tight">AI 记忆</h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-muted">
          从你的有效记录中提取，校验后自动保存。系统推断会明确标注，你可以随时更正、停止使用或遗忘。
        </p>
      </header>
      <div className="my-6 flex items-center justify-between gap-3">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger
            ref={statusTrigger}
            aria-label="记忆状态"
            className="w-40"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="active">有效</SelectItem>
            <SelectItem value="needs_review">需重核</SelectItem>
            <SelectItem value="stopped">已停止</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={() => void list.refetch()} disabled={list.isFetching}>
          刷新
        </Button>
      </div>
      {list.isPending && (
        <p role="status" className="py-12 text-center text-muted">
          正在读取记忆…
        </p>
      )}
      {list.isError && (
        <p role="alert" className="card text-danger">
          记忆暂时无法读取，请刷新重试。
        </p>
      )}
      {!list.isPending && !list.isError && !items.length && (
        <div className="rounded-2xl border border-dashed border-line px-6 py-16 text-center">
          <h2 className="font-medium">这里还没有记忆</h2>
          <p className="mt-2 text-sm text-muted">你仍然可以正常记录和交流。</p>
          <Link to="/records" className="btn mt-5">
            去我的记录
          </Link>
        </div>
      )}
      <div className="space-y-4">
        {items.map((row) => (
          <article
            key={row.id}
            className="memory-card rounded-2xl border border-line bg-white p-5 page:p-7"
          >
            <p
              className={`mb-3 text-xs font-medium ${row.claim_type === 'system_inference' ? 'text-status' : 'text-muted'}`}
            >
              {claimNames[row.claim_type]}
            </p>
            <h2 className="whitespace-pre-wrap text-lg leading-8 font-medium wrap-anywhere">
              {row.source_available
                ? row.content
                : '来源已变化或不可用，需要重新核对'}
            </h2>
            <dl className="mt-5 grid gap-2 text-xs leading-5 text-muted page:grid-cols-2">
              <div>
                <dt className="inline">发生时间：</dt>
                <dd className="inline">
                  {row.event_time
                    ? new Date(row.event_time).toLocaleString()
                    : '未知'}
                </dd>
              </div>
              <div>
                <dt className="inline">记录时间：</dt>
                <dd className="inline">
                  {new Date(row.recorded_at).toLocaleString()}
                </dd>
              </div>
              <div>
                <dt className="inline">版本：</dt>
                <dd className="inline">{row.version}</dd>
              </div>
              <div>
                <dt className="inline">范围：</dt>
                <dd className="inline">你的个人记忆</dd>
              </div>
            </dl>
            <ul
              aria-label="记忆来源"
              className="mt-4 space-y-1 border-t border-line pt-3 text-xs text-muted"
            >
              {row.source_refs.map((source) => (
                <li key={source.source_id} className="wrap-anywhere">
                  {sourceNames[source.source_type] ?? '资料'} ·{' '}
                  {source.source_id} · 版本 {source.source_version}
                </li>
              ))}
            </ul>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button
                disabled={!row.source_available || row.status !== 'active'}
                onClick={(event) =>
                  setSelected({
                    row,
                    action: 'edit',
                    opener: event.currentTarget,
                  })
                }
              >
                <Pencil size={16} aria-hidden="true" />
                更正
              </Button>
              <Button
                disabled={!row.source_available || row.status !== 'active'}
                onClick={(event) =>
                  setSelected({
                    row,
                    action: 'stop',
                    opener: event.currentTarget,
                  })
                }
              >
                停止使用
              </Button>
              <Button
                className="btn btn-ghost text-danger"
                onClick={(event) =>
                  setSelected({
                    row,
                    action: 'forget',
                    opener: event.currentTarget,
                  })
                }
              >
                <Trash2 size={16} aria-hidden="true" />
                遗忘
              </Button>
            </div>
          </article>
        ))}
      </div>
      {list.hasNextPage && (
        <Button
          className="btn mt-5"
          disabled={list.isFetchingNextPage}
          onClick={() => void list.fetchNextPage()}
        >
          加载更多
        </Button>
      )}
      {selected && (
        <MemoryAction
          key={selected.row.id + selected.action}
          {...selected}
          close={() => setSelected(null)}
          restoreFocus={() => {
            const target = selected.opener
            if (target.isConnected && !target.disabled) target.focus()
            else statusTrigger.current?.focus()
          }}
        />
      )}
    </section>
  )
}

function MemoryAction({
  row,
  action,
  close,
  restoreFocus,
}: {
  row: Memory
  action: 'edit' | 'forget' | 'stop'
  close: () => void
  restoreFocus: () => void
}) {
  const client = useQueryClient()
  const identity = useQuery({
    queryKey: ['identity'],
    queryFn: ({ signal }) => getIdentity(signal),
  })
  const preview = useQuery({
    queryKey: ['memory-preview', row.id],
    enabled: action === 'forget',
    queryFn: ({ signal }) =>
      request(
        `/memories/${row.id}/deletion-preview`,
        z.object({
          memory_id: z.string(),
          version: z.number(),
          delete_original: z.literal(false),
          source_refs: z.array(sourceSchema),
        }),
        { signal },
      ),
  })
  const [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [version, setVersion] = useState<number | null>(null)
  const [latest, setLatest] = useState<Memory | null>(null)
  const [discard, setDiscard] = useState(false)
  const pending = useRef<{ key: string; body: unknown } | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const form = useForm({
    defaultValues: { content: row.content },
    validators: {
      onSubmit: z.object({ content: z.string().trim().min(1).max(1200) }),
    },
    onSubmit: ({ value }) =>
      mutation.mutate({
        expected_version: version ?? row.version,
        content: value.content,
      }),
  })
  const blocker = useBlocker({
    shouldBlockFn: () => action === 'edit' && form.state.isDirty,
    withResolver: true,
    enableBeforeUnload: () => action === 'edit' && form.state.isDirty,
  })
  const mutation = useMutation({
    mutationFn: async (body: unknown) => {
      if (
        pending.current &&
        JSON.stringify(pending.current.body) !== JSON.stringify(body)
      )
        throw new Error('请先重试上次操作以核对保存结果，编辑内容已保留。')
      pending.current ??= { key: crypto.randomUUID(), body }
      try {
        const result = await request(
          `/memories/${row.id}`,
          z.union([
            memorySchema,
            z.object({ deletion_id: z.string(), status: z.string() }),
          ]),
          {
            method: action === 'forget' ? 'DELETE' : 'PATCH',
            body: pending.current.body,
            key: pending.current.key,
            csrf: identity.data?.csrf_token,
            signal: AbortSignal.timeout(15000),
          },
        )
        if ('deletion_id' in result && result.status !== 'completed')
          throw new Error('删除已阻断，清理尚未完成，请重试。')
      } catch (cause) {
        setUncertain(!(cause instanceof RequestError && cause.status < 500))
        if (cause instanceof RequestError && cause.status < 500)
          pending.current = null
        if (cause instanceof RequestError && cause.status === 409)
          setLatest(await request(`/memories/${row.id}`, memorySchema))
        throw cause
      }
    },
    onSuccess: async () => {
      form.reset()
      await client.invalidateQueries({ queryKey: ['memories'] })
      client.removeQueries({ queryKey: ['memory-preview'] })
      if (action === 'forget') notifyPrivateChange({ type: 'records-deleted' })
      close()
    },
    onError: (cause) =>
      setError(
        cause instanceof RequestError && cause.status === 409
          ? '版本冲突，编辑内容已保留。请核对最新内容后重试。'
          : cause instanceof RequestError
            ? cause.message + ' 结果尚未确认时，请重试核对后再继续编辑。'
            : '操作尚未确认，请重试。你的编辑已保留。',
      ),
  })
  const title =
    action === 'edit'
      ? '更正这条记忆'
      : action === 'forget'
        ? '遗忘这条记忆？'
        : '停止使用这条记忆？'
  const attemptClose = () => {
    if (mutation.isPending) return
    if (form.state.isDirty) setDiscard(true)
    else close()
  }
  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open) attemptClose()
        }}
      >
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            restoreFocus()
          }}
        >
          <DialogTitle className="text-xl font-semibold">{title}</DialogTitle>
          <DialogDescription className="mt-3 text-sm leading-6 text-muted">
            {action === 'forget'
              ? '将清除这条记忆及对应候选，保留原始记录。为防止它再次出现，也会停止从下列来源再次提取。'
              : '你的更正会立即生效，并停止从这些来源再次提取。原始记录保持不变。'}
          </DialogDescription>
          {action === 'forget' && (
            <div className="mt-4 text-xs text-muted">
              {preview.isPending ? (
                <p role="status">正在核对遗忘范围…</p>
              ) : preview.isError ? (
                <p role="alert">范围读取失败，请关闭后重试。</p>
              ) : (
                preview.data?.source_refs.map((s) => (
                  <p key={s.source_id} className="wrap-anywhere">
                    {sourceNames[s.source_type]} · {s.source_id}
                  </p>
                ))
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="mt-4 text-sm text-danger">
              {error}
            </p>
          )}
          {latest && (
            <div className="card mt-4 text-sm">
              <p>
                最新版本 {latest.version}：{latest.content || '来源不可用'}
              </p>
              <Button
                className="btn mt-3"
                disabled={action !== 'forget' && !latest.source_available}
                onClick={() => {
                  setVersion(latest.version)
                  setLatest(null)
                  setError(
                    action === 'forget'
                      ? '已采用核对后的版本，请确认遗忘。'
                      : '已采用最新版本号，你的编辑内容保持不变。',
                  )
                }}
              >
                {action === 'forget'
                  ? '已核对最新版本'
                  : '已核对，保留我的修改'}
              </Button>
            </div>
          )}
          {action === 'edit' ? (
            <form
              className="mt-5"
              onSubmit={(event) => {
                event.preventDefault()
                void form.handleSubmit()
              }}
            >
              <form.Field name="content">
                {(field) => (
                  <label className="block text-sm">
                    更正内容
                    <Textarea
                      ref={editor}
                      disabled={mutation.isPending || uncertain}
                      className="field mt-2 min-h-36"
                      value={field.state.value}
                      onChange={(event) =>
                        field.handleChange(event.target.value)
                      }
                      onBlur={field.handleBlur}
                      maxLength={1200}
                    />
                    {field.state.meta.errors.length > 0 && (
                      <p role="alert">请输入 1–1200 字的内容。</p>
                    )}
                  </label>
                )}
              </form.Field>
              <div className="mt-5 flex gap-2">
                <Button
                  type="submit"
                  className="btn btn-primary"
                  disabled={mutation.isPending || !!latest}
                >
                  保存更正
                </Button>
                <Button onClick={attemptClose}>取消</Button>
              </div>
            </form>
          ) : (
            <div className="mt-5 flex gap-2">
              <Button
                className="btn btn-danger"
                disabled={
                  mutation.isPending ||
                  !!latest ||
                  (action === 'forget' && !preview.data)
                }
                onClick={() =>
                  mutation.mutate(
                    action === 'forget'
                      ? {
                          expected_version: version ?? preview.data?.version,
                          confirmed: true,
                        }
                      : {
                          expected_version: version ?? row.version,
                          status: 'stopped',
                        },
                  )
                }
              >
                {action === 'forget' ? '确认遗忘' : '确认停止'}
              </Button>
              <DialogClose asChild>
                <Button disabled={mutation.isPending}>取消</Button>
              </DialogClose>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={discard || blocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open) {
            setDiscard(false)
            if (blocker.status === 'blocked') blocker.reset()
          }
        }}
      >
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            editor.current?.focus()
          }}
        >
          <DialogTitle>放弃未保存的更正？</DialogTitle>
          <DialogDescription className="my-4 text-sm text-muted">
            离开后，这次编辑不会保存。
          </DialogDescription>
          <Button
            className="btn btn-danger"
            onClick={() => {
              form.reset()
              if (blocker.status === 'blocked') blocker.proceed()
              else close()
            }}
          >
            放弃修改
          </Button>
          <DialogClose asChild>
            <Button className="btn ml-2">继续编辑</Button>
          </DialogClose>
        </DialogContent>
      </Dialog>
    </>
  )
}
