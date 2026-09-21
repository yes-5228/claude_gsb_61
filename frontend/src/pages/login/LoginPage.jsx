import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext.jsx'
import { Alert } from '../../components/common/Feedback.jsx'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (!username.trim() || !password) {
      setError({ message: '请输入账号和密码' })
      return
    }
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
      const dest = location.state?.from || '/measurements'
      navigate(dest, { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card card" onSubmit={submit}>
        <div className="brand">
          <div className="brand-logo">AQ</div>
          <div>
            <div className="brand-title">空气监测数据平台</div>
            <div className="brand-sub">岗位分级录入 · 请使用分配的账号登录</div>
          </div>
        </div>

        {error ? <Alert tone="error">{error.message}</Alert> : null}

        <label className="field">
          <span className="field-label">登录账号</span>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="如: wangmin"
            autoComplete="username"
          />
        </label>
        <label className="field">
          <span className="field-label">登录密码</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
            autoComplete="current-password"
          />
        </label>

        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? '登录中...' : '登 录'}
        </button>

        <div className="small muted login-hint">
          演示账号: admin / lijing / wangmin / chenzq / zhaoyu,
          初始密码 air123456(sunqian 为停用账号)
        </div>
      </form>
    </div>
  )
}
