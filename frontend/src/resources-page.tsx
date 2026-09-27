import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { request } from './account-api'
import { exerciseSchema } from './support-api'

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
    <div className="support-content">
      <header className="support-header">
        <h1>支持资源</h1>
      </header>
      <nav className="resource-tabs" aria-label="资源分类">
        <Link
          to="/resources"
          search={{ tab: 'exercise' }}
          aria-current={tab === 'exercise' ? 'page' : undefined}
        >
          练习
        </Link>
        <Link
          to="/resources"
          search={{ tab: 'support' }}
          aria-current={tab === 'support' ? 'page' : undefined}
        >
          现实支持
        </Link>
      </nav>
      {tab === 'exercise' ? (
        <section className="resource-card">
          <p className="eyebrow">一个可以随时结束的片刻</p>
          <h2>注意身边的事物</h2>
          <p>
            文字步骤，不用先聊天。可以跳过，也可以随时退出；不保存练习历史。
          </p>
          {exercise.isError ? (
            <>
              <p role="alert">资源读取失败。</p>
              <button onClick={() => void exercise.refetch()}>重试</button>
            </>
          ) : exercise.data?.available ? (
            <>
              <p>合成演示内容，尚未专业审阅。</p>
              <Link
                className="primary"
                to="/resources/exercises/$exerciseId"
                params={{ exerciseId: 'attention' }}
              >
                查看练习
              </Link>
            </>
          ) : (
            <p role="status">练习内容待审阅，暂未开放。</p>
          )}
        </section>
      ) : (
        <section className="support-empty">
          <h2>暂无已核实的校内值班信息</h2>
          {support.isError ? (
            <>
              <p role="alert">无法核对资源状态。</p>
              <button onClick={() => void support.refetch()}>重试</button>
            </>
          ) : (
            <p>{support.data?.message ?? '正在读取…'}</p>
          )}
          <p className="text-muted">
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
    <Link to="/chat/$sessionId" params={{ sessionId: from }}>
      退出练习，返回对话
    </Link>
  ) : (
    <Link to="/resources">退出练习，返回资源</Link>
  )
  const content = query.data
  return (
    <div className="support-content">
      <header className="support-header">
        <span>支持资源 / 练习</span>
        {exit}
      </header>
      {exerciseId !== 'attention' ? (
        <p role="alert">找不到此练习。</p>
      ) : query.isError ? (
        <>
          <p role="alert">无法读取练习。</p>
          <button onClick={() => void query.refetch()}>重试</button>
        </>
      ) : !content ? (
        <p>正在读取…</p>
      ) : !content.available ? (
        <p role="status">练习内容待审阅，暂未开放。</p>
      ) : (
        <section className="support-empty exercise-stage">
          <p className="eyebrow">{content.version} · 合成演示，未经专业审阅</p>
          {step < 0 ? (
            <>
              <h1 ref={focus} tabIndex={-1}>
                {content.title}
              </h1>
              <p>
                按自己的节奏留意身边。无需闭眼或屏息，跳过不算失败。不保存历史。
              </p>
              <button className="primary" onClick={() => setStep(0)}>
                开始练习
              </button>
            </>
          ) : step < content.steps.length ? (
            <>
              <p role="status">
                第 {step + 1} / {content.steps.length} 步
              </p>
              <progress
                value={step + 1}
                max={content.steps.length}
                aria-label="练习进度"
              />
              <h1 ref={focus} tabIndex={-1}>
                {content.steps[step]}
              </h1>
              <p>可以按自己的节奏进行，随时退出。</p>
              <div className="flex flex-wrap justify-center gap-4">
                <button onClick={() => setStep(step + 1)}>跳过</button>
                <button className="primary" onClick={() => setStep(step + 1)}>
                  下一步
                </button>
              </div>
            </>
          ) : (
            <>
              <h1 ref={focus} tabIndex={-1}>
                练习到这里结束
              </h1>
              <p>无需记录或评价这次体验。</p>
              <Link to="/resources">返回资源</Link>
              <Link to="/chat">主动开始一次对话</Link>
            </>
          )}
        </section>
      )}
    </div>
  )
}
