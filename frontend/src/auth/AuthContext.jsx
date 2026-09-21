import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { fetchMe, login as loginRequest } from '../api/auth.js'
import { authEvent, getToken, setToken } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setReady(true)
      return null
    }
    try {
      const me = await fetchMe()
      setUser(me)
      return me
    } catch {
      setToken('')
      setUser(null)
      return null
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    loadMe()
  }, [loadMe])

  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null)
    }
    authEvent.addEventListener('unauthorized', onUnauthorized)
    return () => authEvent.removeEventListener('unauthorized', onUnauthorized)
  }, [])

  const login = useCallback(async (username, password) => {
    const payload = await loginRequest(username, password)
    setToken(payload.token)
    setUser(payload.user)
    return payload.user
  }, [])

  const logout = useCallback(() => {
    setToken('')
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      ready,
      login,
      logout,
      reload: loadMe,
      isAdmin: Boolean(user?.is_admin),
      canProxy: Boolean(user?.can_proxy),
      scope: user?.scope ?? null
    }),
    [user, ready, login, logout, loadMe]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
