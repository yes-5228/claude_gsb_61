import http from './client.js'

export const listPositions = () => http.get('/admin/positions')
export const createPosition = (payload) => http.post('/admin/positions', payload)
export const updatePosition = (payload) => http.put(`/admin/positions/${payload.id}`, payload)
export const createScope = (positionId, payload) =>
  http.post(`/admin/positions/${positionId}/scopes`, payload)

export const listUsers = () => http.get('/admin/users')
export const createUser = (payload) => http.post('/admin/users', payload)
export const updateUser = (payload) => http.put(`/admin/users/${payload.id}`, payload)
