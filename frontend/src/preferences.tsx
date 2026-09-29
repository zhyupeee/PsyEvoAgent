import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { request } from './account-api'
import { preferencesQuery, preferencesSchema } from './support-api'

export function Preferences({ csrf }: { csrf: string }) {
  const query = useQuery(preferencesQuery)
  return (
    <section className="support-content card mb-8 grid gap-4">
      <h2 className="text-xl font-semibold">交流与显示偏好</h2>
      {query.isError ? (
        <>
          <p role="alert" className="text-danger">
            偏好读取失败。
          </p>
          <button
            className="btn justify-self-start"
            onClick={() => void query.refetch()}
          >
            重新读取
          </button>
        </>
      ) : query.data ? (
        <PreferenceForm
          key={query.data.version}
          saved={query.data}
          csrf={csrf}
        />
      ) : (
        <p className="text-muted">正在读取偏好…</p>
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
          <label className="grid gap-1 text-sm font-medium">
            交流方式
            <select
              className="field max-w-xs"
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
          <label className="grid gap-1 text-sm font-medium">
            字号
            <select
              className="field max-w-xs"
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
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 accent-status"
              checked={field.state.value}
              onChange={(e) => field.handleChange(e.target.checked)}
            />{' '}
            减少动画
          </label>
        )}
      </form.Field>
      <form.Field name="display_preferences.hide_titles">
        {(field) => (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 accent-status"
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
        <p role="alert" className="text-sm text-danger">
          未保存。可能存在版本冲突，请重新读取后再试。
        </p>
      ) : null}
      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={mutation.isPending}
        >
          保存偏好
        </button>
        <button
          type="button"
          className="btn"
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
