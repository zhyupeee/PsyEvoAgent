import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { HeartHandshake, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { request } from './account-api'
import { exerciseSchema } from './support-api'

const tabLinkClass =
  '-mb-px inline-flex min-h-11 items-center border-b-2 border-transparent px-1 text-sm font-medium text-muted no-underline transition-colors hover:text-ink aria-[current=page]:border-status aria-[current=page]:text-ink'

const exerciseQuery = {
  queryKey: ['exercise', 'attention'],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    request('/resources/exercises/attention', exerciseSchema, { signal }),
}
export function ResourcesPage({ tab }: { tab: 'exercise' | 'support' }) {
  const exercise = useQuery(exerciseQuery)
  const support = useQuery({
    queryKey: ['support-resources'],
    queryFn: ({ signal }) =>
      request(
        '/resources/support',
        z.object({
          message: z.string(),
          checked_at: z.string().nullable(),
          items: z.array(z.unknown()),
        }),
        { signal },
      ),
    enabled: tab === 'support',
  })
  return (
    <div className="support-content mx-auto w-full max-w-[1000px] pt-6 pb-12 page:pt-8">
      <header className="support-header mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">支持资源</h1>
      </header>
      <nav
        className="resource-tabs flex flex-wrap gap-x-6 gap-y-1 border-b border-line"
        aria-label="资源分类"
      >
        <Link
          to="/resources"
          search={{ tab: 'exercise' }}
          className={tabLinkClass}
          aria-current={tab === 'exercise' ? 'page' : undefined}
        >
          练习
        </Link>
        <Link
          to="/resources"
          search={{ tab: 'support' }}
          className={tabLinkClass}
          aria-current={tab === 'support' ? 'page' : undefined}
        >
          现实支持
        </Link>
      </nav>
      {tab === 'exercise' ? (
        <section className="resource-card card mt-6 grid justify-items-start gap-4 p-4 page:p-6">
          <p className="eyebrow">一个可以随时结束的片刻</p>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <Sparkles size={20} aria-hidden="true" className="text-status" />
            注意身边的事物
          </h2>
          <p className="text-sm leading-6 text-muted">
            文字步骤，不用先聊天。可以跳过，也可以随时退出；不保存练习历史。
          </p>
          {exercise.isError ? (
            <>
              <p role="alert" className="text-sm text-danger">
                资源读取失败。
              </p>
              <button className="btn" onClick={() => void exercise.refetch()}>
                重试
              </button>
            </>
          ) : exercise.data?.available ? (
            <>
              <p className="text-sm text-muted">合成演示内容，尚未专业审阅。</p>
              <Link
                className="primary btn btn-primary"
                to="/resources/exercises/$exerciseId"
                params={{ exerciseId: 'attention' }}
              >
                查看练习
              </Link>
            </>
          ) : (
            <p role="status" className="text-sm text-muted">
              练习内容待审阅，暂未开放。
            </p>
          )}
        </section>
      ) : (
        <section className="support-empty mx-auto grid min-h-[55dvh] w-full max-w-[560px] content-center justify-items-center gap-4 py-14 text-center">
          <div className="grid h-14 w-14 place-items-center rounded-full bg-accent text-status">
            <HeartHandshake size={26} aria-hidden="true" />
          </div>
          <h2 className="text-xl font-semibold">暂无已核实的校内值班信息</h2>
          {support.isError ? (
            <>
              <p role="alert" className="text-sm text-danger">
                无法核对资源状态。
              </p>
              <button className="btn" onClick={() => void support.refetch()}>
                重试
              </button>
            </>
          ) : (
            <p className="text-sm leading-6 text-muted">
              {support.data?.message ?? '正在读取…'}
            </p>
          )}
          <p className="text-xs text-muted">
            不会自动联系他人，也不提供值守或转介承诺。
          </p>
        </section>
      )}
    </div>
  )
}

export function ExercisePage({
  exerciseId,
  from,
}: {
  exerciseId: string
  from?: string
}) {
  const query = useQuery({
    ...exerciseQuery,
    enabled: exerciseId === 'attention',
  })
  const [step, setStep] = useState(-1)
  const focus = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    focus.current?.focus()
  }, [step])
  const exit = from ? (
    <Link
      className="btn-ghost"
      to="/chat/$sessionId"
      params={{ sessionId: from }}
    >
      退出练习，返回对话
    </Link>
  ) : (
    <Link className="btn-ghost" to="/resources">
      退出练习，返回资源
    </Link>
  )
  const content = query.data
  return (
    <div className="support-content mx-auto w-full max-w-[1000px] pt-6 pb-12 page:pt-8">
      <header className="support-header flex min-h-11 items-center justify-between gap-3 border-b border-line pb-4">
        <span className="text-xs font-medium text-muted">支持资源 / 练习</span>
        {exit}
      </header>
      {exerciseId !== 'attention' ? (
        <p role="alert" className="mt-8 text-sm text-danger">
          找不到此练习。
        </p>
      ) : query.isError ? (
        <>
          <p role="alert" className="mt-8 text-sm text-danger">
            无法读取练习。
          </p>
          <button className="btn mt-3" onClick={() => void query.refetch()}>
            重试
          </button>
        </>
      ) : !content ? (
        <p className="mt-8 text-sm text-muted">正在读取…</p>
      ) : !content.available ? (
        <p role="status" className="mt-8 text-sm text-muted">
          练习内容待审阅，暂未开放。
        </p>
      ) : (
        <section className="support-empty exercise-stage mx-auto mt-8 grid min-h-[55dvh] w-full max-w-[640px] content-center justify-items-center gap-5 rounded-2xl border border-line bg-white px-4 py-10 text-center page:px-10 page:py-14">
          <p className="eyebrow">{content.version} · 合成演示，未经专业审阅</p>
          {step < 0 ? (
            <>
              <h1
                ref={focus}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-tight"
              >
                {content.title}
              </h1>
              <p className="max-w-md text-sm leading-6 text-muted">
                按自己的节奏留意身边。无需闭眼或屏息，跳过不算失败。不保存历史。
              </p>
              <button
                className="primary btn btn-primary"
                onClick={() => setStep(0)}
              >
                开始练习
              </button>
            </>
          ) : step < content.steps.length ? (
            <>
              <p role="status" className="text-sm text-muted">
                第 {step + 1} / {content.steps.length} 步
              </p>
              <progress
                className="h-1.5 w-full max-w-xs accent-status"
                value={step + 1}
                max={content.steps.length}
                aria-label="练习进度"
              />
              <h1
                ref={focus}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-tight"
              >
                {content.steps[step]}
              </h1>
              <p className="text-sm leading-6 text-muted">
                可以按自己的节奏进行，随时退出。
              </p>
              <div className="flex flex-wrap justify-center gap-4">
                <button className="btn" onClick={() => setStep(step + 1)}>
                  跳过
                </button>
                <button
                  className="primary btn btn-primary"
                  onClick={() => setStep(step + 1)}
                >
                  下一步
                </button>
              </div>
            </>
          ) : (
            <>
              <h1
                ref={focus}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-tight"
              >
                练习到这里结束
              </h1>
              <p className="text-sm leading-6 text-muted">
                无需记录或评价这次体验。
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                {from ? (
                  <Link
                    className="btn btn-primary"
                    to="/chat/$sessionId"
                    params={{ sessionId: from }}
                  >
                    返回原对话
                  </Link>
                ) : (
                  <Link className="btn btn-primary" to="/resources">
                    返回资源
                  </Link>
                )}
                <Link className="btn" to="/chat">
                  主动开始一次对话
                </Link>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
