import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { request } from './account-api'
import { preferencesQuery, preferencesSchema } from './support-api'

export function Preferences({ csrf }: { csrf: string }) {
  const query = useQuery(preferencesQuery)
  return (
    <section className="support-content mb-8 rounded-lg border border-line bg-white p-6">
      <h2 className="mb-4 text-xl font-semibold">交流与显示偏好</h2>
      {query.isError ? (
        <>
          <p role="alert">偏好读取失败。</p>
          <button onClick={() => void query.refetch()}>重新读取</button>
        </>
      ) : query.data ? (
        <PreferenceForm
          key={query.data.version}
          saved={query.data}
          csrf={csrf}
        />
      ) : (
        <p>正在读取偏好…</p>
      )}
    </section>
  )
}
function PreferenceForm({
  saved,
  csrf,
}: {
  saved: z.infer<typeof preferencesSchema>
  csrf: string
}) {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: (value: typeof saved) =>
      request('/me/preferences', preferencesSchema, {
        method: 'PATCH',
        csrf,
        body: {
          expected_version: saved.version,
          age_band: saved.age_band,
          mode: value.mode,
          display_preferences: value.display_preferences,
        },
      }),
    onSuccess: (value) => client.setQueryData(['preferences'], value),
  })
  const form = useForm({
    defaultValues: saved,
    onSubmit: async ({ value }) => {
      await mutation
        .mutateAsync(preferencesSchema.parse(value))
        .catch(() => undefined)
    },
  })
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        void form.handleSubmit()
      }}
      className="grid gap-4"
    >
      <form.Field name="mode">
        {(field) => (
          <label>
            交流方式
            <select
              value={field.state.value}
              onChange={(e) =>
                field.handleChange(
                  z.enum(['listen', 'explore']).parse(e.target.value),
                )
              }
            >
              <option value="listen">先倾听</option>
              <option value="explore">一起想办法</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="display_preferences.font_size">
        {(field) => (
          <label>
            字号
            <select
              value={field.state.value}
              onChange={(e) =>
                field.handleChange(
                  z.enum(['normal', 'large']).parse(e.target.value),
                )
              }
            >
              <option value="normal">标准</option>
              <option value="large">大字号</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="display_preferences.reduced_motion">
        {(field) => (
          <label>
            <input
              type="checkbox"
              checked={field.state.value}
              onChange={(e) => field.handleChange(e.target.checked)}
            />{' '}
            减少动画
          </label>
        )}
      </form.Field>
      <form.Field name="display_preferences.hide_titles">
        {(field) => (
          <label>
            <input
              type="checkbox"
              checked={field.state.value}
              onChange={(e) => field.handleChange(e.target.checked)}
            />{' '}
            隐藏对话标题
          </label>
        )}
      </form.Field>
      <p className="text-sm text-muted">
        当前已保存版本：{saved.version}。改变交流方式从下一次发送生效。
      </p>
      {mutation.isError ? (
        <p role="alert">未保存。可能存在版本冲突，请重新读取后再试。</p>
      ) : null}
      <div className="flex flex-wrap gap-3">
        <button type="submit" disabled={mutation.isPending}>
          保存偏好
        </button>
        <button
          type="button"
          onClick={() =>
            void client.invalidateQueries({ queryKey: ['preferences'] })
          }
        >
          重新读取偏好
        </button>
      </div>
    </form>
  )
}
