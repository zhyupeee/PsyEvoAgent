import { useForm } from '@tanstack/react-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { z } from 'zod'
import { request, RequestError } from './account-api'
import { Button } from './components/ui/button'

export const modelSettingsSchema = z.object({
  version: z.number(),
  mode: z.enum(['official', 'custom']),
  official: z.object({ model: z.string(), available: z.boolean() }),
  credential_storage_available: z.boolean(),
  custom: z.object({
    base_url: z.string(),
    model: z.string(),
    has_key: z.boolean(),
    deadline_seconds: z.number(),
    max_output_tokens: z.number(),
  }),
})
type Saved = z.infer<typeof modelSettingsSchema>
const formSchema = z
  .object({
    mode: z.enum(['official', 'custom']),
    base_url: z.string().max(500),
    model: z.string().max(200),
    api_key: z.string().max(4096),
    deadline_seconds: z.number().min(1).max(120),
    max_output_tokens: z.number().int().min(1).max(4096),
  })
  .refine(
    (value) =>
      value.mode === 'official' ||
      (value.base_url.startsWith('https://') && value.model.trim().length > 0),
    { message: '请填写 HTTPS API 地址和模型名称。' },
  )
const key = ['model-settings']
const inputStyle = 'field'

export function modelFailure(reason?: string | null) {
  switch (reason) {
    case 'provider_test_active':
    case 'provider_test_running':
      return '模型配置测试正在进行，请稍后检查原请求。'
    case 'provider_test_throttled':
      return '测试过于频繁，请等待十秒后再试。'
    case 'provider_configuration_revoked':
    case 'identity_revoked':
    case 'cancelled':
      return '本次测试已取消。'
    case 'run_active':
      return '请等当前回答完成后再测试模型配置。'
    case 'provider_authentication':
      return '模型服务拒绝了 API Key，请在模型配置中核对凭据。'
    case 'provider_model_unavailable':
      return '模型或接口不可用，请核对 API 地址和模型名。'
    case 'rate_limit':
      return '模型服务暂时限流，请稍后重试。'
    case 'deadline':
      return '模型响应超时，请稍后重试或调整超时设置。'
    case 'configuration_mismatch':
    case 'provider_configuration_invalid':
    case 'provider_configuration_unavailable':
      return '模型配置未能加载，请检查设置或重新启动本地后端。'
    case 'provider_address_blocked':
      return 'API 地址无法安全连接，请使用可公开访问的 HTTPS 地址。'
    case 'schema_invalid':
      return '模型返回的内容格式不符合要求，请更换兼容模型。'
    case 'output_too_large':
      return '回答超出长度限制，未能完整显示。请尝试要求更简短的回答。'
    case 'truncated':
      return '模型未完整生成回答，可能已达到输出上限。请要求更简短的回答或调整输出上限。'
    case 'partial_stream':
      return '模型响应传输中断或不完整，请稍后重试。'
    case 'usage_over_reservation':
      return '模型报告的用量超出本次预算，请要求更简短的回答或调整输出上限。'
    case 'usage_unknown':
      return '模型未返回用量信息，暂时无法使用此接口。'
    case 'provider_key_required_for_address_change':
      return '修改 API 地址后需要重新填写 Key。'
    case 'provider_encryption_unavailable':
      return '服务器尚未配置密钥加密存储，请联系维护者。'
    case 'provider_settings_incomplete':
      return '请完整填写 API 地址、模型名和 Key。'
    case 'provider_not_configured':
      return '模型服务尚未启用，请联系维护者。'
    case 'version_conflict':
      return '配置已被其他页面修改。已刷新版本，请核对后再次保存。'
    default:
      return '模型请求未完成，请检查配置或稍后重试。'
  }
}

export function ModelSettings({ csrf }: { csrf: string }) {
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      request('/me/model-settings', modelSettingsSchema, { signal }),
    refetchInterval: 5000,
  })
  return (
    <section className="settings-card card mb-6 grid gap-4">
      <h2 className="text-xl font-semibold">模型配置</h2>
      <p className="text-sm text-muted">选择为聊天和自动标题提供模型的方式。</p>
      {query.data ? (
        <ModelForm saved={query.data} csrf={csrf} />
      ) : query.isError ? (
        <p role="alert" className="text-sm text-danger">
          配置读取失败。
          <button
            className="btn-ghost ml-1"
            onClick={() => void query.refetch()}
          >
            重新读取
          </button>
        </p>
      ) : (
        <p role="status" className="text-sm text-muted">
          正在读取模型配置…
        </p>
      )}
    </section>
  )
}

function initial(saved: Saved) {
  return {
    mode: saved.mode,
    base_url: saved.custom.base_url,
    model: saved.custom.model,
    api_key: '',
    deadline_seconds: saved.custom.deadline_seconds,
    max_output_tokens: saved.custom.max_output_tokens,
  }
}

function ModelForm({ saved, csrf }: { saved: Saved; csrf: string }) {
  const client = useQueryClient()
  const [confirmation, setConfirmation] = useState<number | null>(null)
  const [editingVersion, setEditingVersion] = useState(saved.version)
  const [notice, setNotice] = useState('')
  const save = useMutation({
    gcTime: 0,
    mutationFn: async () => {
      const value = form.state.values
      return request('/me/model-settings', modelSettingsSchema, {
        method: 'PATCH',
        csrf,
        body: {
          expected_version: editingVersion,
          mode: value.mode,
          ...(value.mode === 'custom'
            ? {
                base_url: value.base_url,
                model: value.model,
                ...(value.api_key ? { api_key: value.api_key } : {}),
                deadline_seconds: value.deadline_seconds,
                max_output_tokens: value.max_output_tokens,
              }
            : {}),
        },
      })
    },
    onSuccess: (value) => {
      client.setQueryData(key, value)
      form.reset(initial(value))
      setEditingVersion(value.version)
      setNotice('已保存。新回答将使用此配置，进行中的回答保持原配置。')
    },
    onError: async (error) => {
      setNotice(
        modelFailure(error instanceof RequestError ? error.code : undefined),
      )
      if (error instanceof RequestError && error.status === 409) {
        await client.invalidateQueries({ queryKey: key })
        const latest = client.getQueryData<Saved>(key)
        if (latest) setEditingVersion(latest.version)
      }
    },
  })
  const form = useForm({
    defaultValues: initial(saved),
    onSubmit: async () => {
      setNotice('')
      if (!formSchema.safeParse(form.state.values).success) {
        setNotice('请核对 HTTPS 地址、模型名称、超时和输出上限。')
        return
      }
      await save.mutateAsync().catch(() => undefined)
    },
  })
  const pendingTest = useRef<{ key: string; version: number } | null>(null)
  const test = useMutation({
    mutationFn: () => {
      if (!pendingTest.current || pendingTest.current.version !== saved.version)
        pendingTest.current = {
          key: crypto.randomUUID(),
          version: saved.version,
        }
      return request(
        '/me/model-settings/test',
        z.object({ passed: z.boolean(), reason: z.string().nullable() }),
        {
          method: 'POST',
          csrf,
          key: pendingTest.current.key,
          body: { expected_version: saved.version },
        },
      )
    },
    onSuccess: (value) => {
      if (value.reason !== 'provider_test_running') pendingTest.current = null
      setNotice(
        value.passed
          ? '测试通过：已收到完整、格式及用量检查通过的响应。'
          : modelFailure(value.reason),
      )
    },
    onError: (error) =>
      setNotice(
        modelFailure(error instanceof RequestError ? error.code : undefined),
      ),
  })
  const remove = useMutation({
    mutationFn: () =>
      request('/me/model-settings', modelSettingsSchema, {
        method: 'DELETE',
        csrf,
        body: { expected_version: confirmation ?? saved.version },
      }),
    onSuccess: (value) => {
      client.setQueryData(key, value)
      form.reset(initial(value))
      setEditingVersion(value.version)
      setConfirmation(null)
      setNotice('个人配置已删除，相关任务已撤销。已切回官方模式。')
    },
    onError: (error) =>
      setNotice(
        modelFailure(error instanceof RequestError ? error.code : undefined),
      ),
  })
  const busy = save.isPending || test.isPending || remove.isPending
  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        void form.handleSubmit()
      }}
    >
      <form.Field name="mode">
        {(field) => (
          <fieldset disabled={busy} className="grid gap-3">
            <legend className="text-sm font-semibold">模型来源</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="model-mode"
                className="h-4 w-4 accent-status"
                checked={field.state.value === 'official'}
                onChange={() => field.handleChange('official')}
              />{' '}
              官方提供
            </label>
            <p className="text-sm text-muted">
              {saved.official.available
                ? `当前模型：${saved.official.model}`
                : '官方模型尚未配置或启用。'}
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="model-mode"
                className="h-4 w-4 accent-status"
                checked={field.state.value === 'custom'}
                onChange={() => field.handleChange('custom')}
              />{' '}
              使用自己的 API
            </label>
          </fieldset>
        )}
      </form.Field>
      <form.Subscribe selector={(state) => state.values.mode}>
        {(mode) =>
          mode === 'custom' ? (
            <fieldset
              disabled={busy}
              className="grid gap-4 rounded-xl border border-line p-4"
            >
              <legend className="px-1 text-sm font-semibold">
                个人 API 配置
              </legend>
              <p className="text-sm text-muted">
                支持 OpenAI Chat Completions
                兼容接口。对话内容会发送给所填服务商，聊天和标题调用可能产生费用。Key
                按账号加密保存。
              </p>
              {!saved.credential_storage_available ? (
                <p role="alert" className="text-sm text-danger">
                  服务器尚未配置密钥加密存储，暂时无法保存个人 Key。
                </p>
              ) : null}
              <form.Field name="base_url">
                {(field) => (
                  <label className="grid gap-1 text-sm font-medium">
                    API Base URL
                    <input
                      className={inputStyle}
                      required
                      type="url"
                      placeholder="https://api.example.com/v1"
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </label>
                )}
              </form.Field>
              <form.Field name="model">
                {(field) => (
                  <label className="grid gap-1 text-sm font-medium">
                    模型名称
                    <input
                      className={inputStyle}
                      required
                      maxLength={200}
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </label>
                )}
              </form.Field>
              <form.Field name="api_key">
                {(field) => (
                  <label className="grid gap-1 text-sm font-medium">
                    API Key
                    <input
                      className={inputStyle}
                      type="password"
                      autoComplete="new-password"
                      maxLength={4096}
                      required={!saved.custom.has_key}
                      placeholder={
                        saved.custom.has_key
                          ? '已配置；留空保留，填写则替换'
                          : '填写服务商提供的 Key'
                      }
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                  </label>
                )}
              </form.Field>
              <details className="rounded-lg border border-line px-3 py-2">
                <summary className="text-sm font-medium text-muted">
                  高级设置
                </summary>
                <div className="grid gap-3 pt-3">
                  <form.Field name="deadline_seconds">
                    {(field) => (
                      <label className="grid gap-1 text-sm font-medium">
                        响应超时（秒）
                        <input
                          className={inputStyle}
                          type="number"
                          required
                          min={1}
                          max={120}
                          value={field.state.value}
                          onChange={(e) =>
                            field.handleChange(e.target.valueAsNumber)
                          }
                        />
                      </label>
                    )}
                  </form.Field>
                  <form.Field name="max_output_tokens">
                    {(field) => (
                      <label className="grid gap-1 text-sm font-medium">
                        最大输出 Token
                        <input
                          className={inputStyle}
                          type="number"
                          required
                          min={1}
                          max={4096}
                          value={field.state.value}
                          onChange={(e) =>
                            field.handleChange(e.target.valueAsNumber)
                          }
                        />
                      </label>
                    )}
                  </form.Field>
                </div>
              </details>
            </fieldset>
          ) : null
        }
      </form.Subscribe>
      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          className="primary btn btn-primary"
          disabled={busy}
        >
          {save.isPending ? '正在保存…' : '保存模型配置'}
        </button>
        <Button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            setNotice('')
            test.mutate()
          }}
        >
          {test.isPending ? '正在测试…' : '测试已保存配置'}
        </Button>
        {saved.custom.has_key ? (
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => setConfirmation(saved.version)}
          >
            删除个人配置
          </button>
        ) : null}
      </div>
      <p className="text-sm text-muted">
        测试将发送一次固定合成内容，不发送历史对话，可能产生费用；保存不会自动测试。
      </p>
      {confirmation !== null ? (
        <div
          role="group"
          aria-label="确认删除个人配置"
          className="grid gap-2 rounded-xl border border-line bg-paper/60 p-4 text-sm"
        >
          <p>
            将删除保存的 Key
            并撤销相关运行中的任务。已生成的聊天内容不受影响。确认删除？
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => remove.mutate()}
            >
              确认删除
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => setConfirmation(null)}
            >
              取消
            </button>
          </div>
        </div>
      ) : null}
      {notice ? (
        <p role="status" className="text-sm text-muted">
          {notice}
        </p>
      ) : null}
    </form>
  )
}
