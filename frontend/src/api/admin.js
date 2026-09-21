import http from './client.js'

export const listPositions = () => http.get('/admin/positions')
export const createPosition = (payload) => http.post('/admin/positions', payload)
export const updatePosition = (id, payload) => http.put(`/admin/positions/${id}`, payload)
export const addScopeVersion = (id, payload) =>
  http.post(`/admin/positions/${id}/scope-versions`, payload)

export const listUsers = () => http.get('/admin/users')
export const createUser = (payload) => http.post('/admin/users', payload)
export const updateUser = (id, payload) => http.put(`/admin/users/${id}`, payload)
