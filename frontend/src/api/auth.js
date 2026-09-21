import http from './client.js'

const STORAGE_KEY = 'aq_operator_token'

let token = localStorage.getItem(STORAGE_KEY) || ''
const listeners = new Set()

export function getToken() {
  return token
}

export function setToken(next) {
  token = next || ''
  if (token) localStorage.setItem(STORAGE_KEY, token)
  else localStorage.removeItem(STORAGE_KEY)
  listeners.forEach((fn) => fn(token))
}

export function onTokenChange(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const fetchMe = () => http.get('/auth/me')
export const fetchUsers = () => http.get('/auth/users')
