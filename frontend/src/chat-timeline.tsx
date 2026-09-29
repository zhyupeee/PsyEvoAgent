import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { z } from 'zod'
import { request } from './account-api'
import { runSchema, type Run } from './support-api'

export function mergeTurns(pages: Run[][], current?: Run | null): Run[] {
  const turns = new Map<string, Run>()
  for (const item of pages.flat()) {
    const prior = turns.get(item.run_id)
    if (!prior || item.version >= prior.version) turns.set(item.run_id, item)
  }
  if (current?.input_id) {
    const prior = turns.get(current.run_id)
    if (!prior || current.version >= prior.version)
      turns.set(current.run_id, current)
  }
  const replaced = new Set(
    [...turns.values()].map((item) => item.parent_run_id).filter(Boolean),
  )
  return [...turns.values()]
    .filter((item) => item.is_current !== false && !replaced.has(item.run_id))
    .sort(
      (a, b) =>
        (a.created_at ?? '').localeCompare(b.created_at ?? '') ||
        a.run_id.localeCompare(b.run_id),
    )
}

export const turnLabels = {
  draft: '尚未发送',
  queued: '已接收，等待响应',
  running: '正在响应',
  completed: '已完成',
  cancelled: '已停止',
  failed: '本次响应失败',
  interrupted: '本次响应中断',
}

export function ChatTimeline({
  sessionId,
  current,
  children,
}: {
  sessionId: string
  current?: Run | null
  children: ReactNode
}) {
  const timeline = useInfiniteQuery({
    queryKey: ['timeline', sessionId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      request(
        `/sessions/${sessionId}/timeline?` +
          new URLSearchParams({
            limit: '20',
            ...(pageParam ? { cursor: pageParam } : {}),
          }),
        z.object({
          items: z.array(runSchema),
          next_cursor: z.string().nullable(),
        }),
        { signal },
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  const { refetch } = timeline
  useEffect(() => {
    void refetch({ cancelRefetch: false })
  }, [current?.run_id, current?.version, refetch])
  const turns = mergeTurns(
    timeline.data?.pages.map((page) => page.items) ?? [],
    current,
  )
  const scroller = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const anchor = useRef<{ id: string; top: number } | null>(null)
  useLayoutEffect(() => {
    const node = scroller.current
    if (!node) return
    if (anchor.current) {
      const item = node.querySelector<HTMLElement>(
        `[data-run-id="${anchor.current.id}"]`,
      )
      if (item)
        node.scrollTop += item.getBoundingClientRect().top - anchor.current.top
      if (!timeline.isFetchingNextPage) anchor.current = null
    } else if (follow.current) node.scrollTop = node.scrollHeight
  }, [timeline.data, timeline.isFetchingNextPage, current])
  return (
    <div
      className="chat-scroll"
      ref={scroller}
      onScroll={() => {
        const node = scroller.current
        if (node)
          follow.current =
            node.scrollHeight - node.scrollTop - node.clientHeight < 80
      }}
    >
      <div className="message-area" aria-label="会话消息">
        {timeline.isError ? (
          <p role="alert">
            消息暂不可用，历史内容已隐藏。
            <button onClick={() => void refetch()}>重试消息</button>
          </p>
        ) : (
          <>
            {timeline.hasNextPage ? (
              <button
                className="earlier-messages"
                disabled={timeline.isFetching}
                onClick={() => {
                  const item =
                    scroller.current?.querySelector<HTMLElement>(
                      '[data-run-id]',
                    )
                  if (item)
                    anchor.current = {
                      id: item.dataset.runId!,
                      top: item.getBoundingClientRect().top,
                    }
                  follow.current = false
                  void timeline.fetchNextPage({ cancelRefetch: false })
                }}
              >
                {timeline.isFetchingNextPage ? '正在加载…' : '加载更早消息'}
              </button>
            ) : null}
            {!turns.length ? (
              <p className="text-muted">
                {timeline.isPending
                  ? '正在读取消息…'
                  : '想说的可以写在下面。每条最多 4000 字；可在“设置”里选择先倾听或一起想办法。'}
              </p>
            ) : null}
            {turns.map((item) => (
              <article
                className="chat-turn"
                data-run-id={item.run_id}
                key={item.run_id}
              >
                {item.input_text ? (
                  <p className="message user-message">{item.input_text}</p>
                ) : null}
                {item.output ? (
                  <p className="message assistant-message">
                    {item.output.text}
                  </p>
                ) : null}
                {item.run_id !== current?.run_id &&
                item.status !== 'completed' ? (
                  <p className="turn-state">{turnLabels[item.status]}</p>
                ) : null}
                {item.run_id === current?.run_id ? children : null}
              </article>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
