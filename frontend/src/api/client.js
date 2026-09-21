import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(message, { status, fields, code } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields || {}
    this.code = code
  }
}

const http = axios.create({ baseURL, timeout: 20000 })

export const TOKEN_KEY = 'aq_auth_token'

export function getToken() {
  return window.localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token)
  else window.localStorage.removeItem(TOKEN_KEY)
}

export const authEvent = new EventTarget()

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const payload = error.response?.data?.error
    const status = error.response?.status
    // 未登录 / 失效 / 被停用: 清除令牌并广播, 由全局守卫跳转登录页
    if (status === 401 && getToken() && !error.config?.url?.includes('/auth/login')) {
      setToken('')
      authEvent.dispatchEvent(new CustomEvent('unauthorized'))
    }
    if (payload) {
      return Promise.reject(
        new ApiError(payload.message || '请求失败', {
          status,
          fields: payload.fields,
          code: payload.code
        })
      )
    }
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new ApiError('请求超时, 请稍后重试'))
    }
    return Promise.reject(
      new ApiError(error.message === 'Network Error' ? '无法连接后端服务' : error.message)
    )
  }
)

/** Convert a filter object into request params, dropping empty values. */
export function toParams(filters = {}) {
  const params = {}
  Object.entries(filters).forEach(([key, value]) => {
    if (value === '' || value === null || value === undefined) return
    if (Array.isArray(value)) {
      if (value.length === 0) return
      params[key] = value.join(',')
      return
    }
    if (typeof value === 'boolean') {
      params[key] = value ? 'true' : 'false'
      return
    }
    params[key] = value
  })
  return params
}

export function downloadFile(url) {
  return axios
    .get(url, { baseURL, responseType: 'blob' })
    .then((response) => response.data)
}

export default http
