import { z } from 'zod'

export class RequestError extends Error {
  constructor(
    public readonly status: number,
    code?: string,
  ) {
    super(
      code === 'invalid_email_code'
        ? '验证码不正确、已过期或已使用，请重新获取。'
        : code === 'invalid_current_password'
          ? '当前密码不正确。'
          : code === 'email_taken'
            ? '该邮箱无法完成注册，请登录或找回密码。'
            : code === 'invalid_credentials'
              ? '邮箱或密码不正确。'
              : status === 429
                ? '尝试次数过多，请稍后再试。'
                : status === 502 || status === 503 || status === 504
                  ? '服务暂时不可用，请稍后重试。'
                  : status === 401
                    ? '登录已失效，请重新登录。'
                    : '请求未完成，请稍后重试。',
    )
  }
}

export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: {
    method?: string
    body?: unknown
    csrf?: string
    signal?: AbortSignal
  } = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    signal: options.signal,
    headers: {
      'Content-Type': 'application/json',
      ...(options.csrf ? { 'X-CSRF-Token': options.csrf } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  if (!response.ok) {
    const error = z
      .object({ code: z.string() })
      .safeParse(await response.json().catch(() => null))
    throw new RequestError(
      response.status,
      error.success ? error.data.code : undefined,
    )
  }
  return schema.parse(response.status === 204 ? null : await response.json())
}

export const identitySchema = z.object({
  user_id: z.string(),
  email: z.string().email(),
  csrf_token: z.string(),
})

export async function getIdentity(signal?: AbortSignal) {
  try {
    return await request('/auth/session', identitySchema, { signal })
  } catch (error) {
    if (error instanceof RequestError && error.status === 401) return null
    throw error
  }
}
