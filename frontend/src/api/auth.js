import http from './client.js'

export const login = (username, password) =>
  http.post('/auth/login', { username, password })

export const fetchMe = () => http.get('/auth/me')
