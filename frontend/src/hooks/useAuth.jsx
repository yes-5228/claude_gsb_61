import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { fetchUsers, getToken, onTokenChange, setToken } from '../api/auth.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(getToken())
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const body = await fetchUsers()
      setUsers(body.items || [])
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUsers()
    const unsubscribe = onTokenChange((next) => {
      setTokenState(next)
      loadUsers()
    })
    return unsubscribe
  }, [loadUsers])

  const currentUser = useMemo(
    () => users.find((item) => item.token === token) || null,
    [users, token]
  )

  const login = useCallback((nextToken) => setToken(nextToken), [])
  const logout = useCallback(() => setToken(''), [])

  const value = { users, currentUser, token, loading, error, login, logout, reload: loadUsers }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
