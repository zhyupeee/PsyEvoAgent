import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Brand } from '../brand'
import { checkHealth } from '../health'

export const Route = createFileRoute('/health')({
  head: () => ({ meta: [{ title: '工程健康检查 · PsyEvoAgent' }] }),
  component: Foundation,
})

const subscribe = () => () => {}

function Foundation() {
  const hydrated = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )
  const [status, setStatus] = useState<
    'idle' | 'checking' | 'ok' | 'stopped' | 'error'
  >('idle')
  const pending = useRef<AbortController | null>(null)
  const startButton = useRef<HTMLButtonElement>(null)
  const error = useRef<HTMLParagraphElement>(null)
  useEffect(() => () => pending.current?.abort(), [])
  useEffect(() => {
    if (status === 'error') error.current?.focus()
  }, [status])

  async function start() {
    if (pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setStatus('checking')
    try {
      await checkHealth(controller.signal)
      if (!controller.signal.aborted) setStatus('ok')
    } catch {
      if (!controller.signal.aborted) setStatus('error')
    } finally {
      if (pending.current === controller) pending.current = null
    }
  }

  function stop() {
    pending.current?.abort()
    pending.current = null
    setStatus('stopped')
    startButton.current?.focus()
  }

  return (
    <main className="mx-auto w-[calc(100%-3rem)] max-w-[1080px]">
      <header className="flex items-center justify-between gap-4 border-b border-line py-8 max-[520px]:flex-col max-[520px]:items-start">
        <Brand />
        <span className="text-[.8rem] tracking-[.07em]">工程验证 / 01.02</span>
      </header>
      <section
        className="max-w-[780px] py-16 pt-20 max-[520px]:pt-12"
        aria-labelledby="title"
      >
        <p className="text-[.8rem] tracking-[.07em] text-muted">
          LOCAL DEVELOPMENT
        </p>
        <h1
          className="my-[1.4rem] font-display text-[clamp(2.5rem,6vw,4.8rem)] leading-[1.22] font-medium"
          id="title"
        >
          先确认连接，
          <br />
          再开始构建。
        </h1>
        <p className="leading-[1.8] text-muted">
          这里用于检查本地开发环境。心理支持服务尚未开放。
        </p>
        <div className="mt-12 border-t-[3px] border-ink pt-6">
          <div>
            <h2 className="m-0 text-[1.1rem] font-bold">API 连通检查</h2>
            <p className="leading-[1.7]">
              仅发送无正文的健康检查请求，不调用模型。
            </p>
          </div>
          <div className="my-6 flex flex-wrap gap-3">
            <button
              className="min-h-12 cursor-pointer border border-ink bg-ink px-[1.4rem] py-[.8rem] text-white aria-disabled:cursor-progress aria-disabled:opacity-[.65] focus-visible:outline-[3px] focus-visible:outline-focus focus-visible:outline-offset-[5px]"
              ref={startButton}
              type="button"
              disabled={!hydrated}
              aria-disabled={status === 'checking'}
              onClick={() => void start()}
            >
              检查连接
            </button>
            {status === 'checking' ? (
              <button
                className="min-h-12 cursor-pointer border border-ink bg-transparent px-[1.4rem] py-[.8rem] text-ink focus-visible:outline-[3px] focus-visible:outline-focus focus-visible:outline-offset-[5px]"
                type="button"
                onClick={stop}
              >
                停止检查
              </button>
            ) : null}
          </div>
          {status === 'error' ? (
            <p
              className="leading-[1.7] text-danger focus-visible:outline-[3px] focus-visible:outline-focus focus-visible:outline-offset-[5px]"
              role="alert"
              tabIndex={-1}
              ref={error}
            >
              连接未完成。请确认 API 已启动，再重试。
            </p>
          ) : (
            <p
              className="min-h-[1.7em] leading-[1.7] text-status"
              role="status"
            >
              {
                {
                  idle: '尚未检查',
                  checking: '正在检查…',
                  ok: 'API 已连接 · S1-STEP02',
                  stopped: '已停止检查',
                }[status]
              }
            </p>
          )}
        </div>
      </section>
      <footer className="flex items-center justify-between gap-4 border-t border-line py-6 text-[.8rem] tracking-[.07em] text-muted">
        <span>开发环境 / 合成验证</span>
        <span>S1-STEP02</span>
      </footer>
    </main>
  )
}
