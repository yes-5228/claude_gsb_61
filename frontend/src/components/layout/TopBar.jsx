import { useCallback } from 'react'
import { health } from '../../api/meta.js'
import { useAsyncData } from '../../hooks/useAsyncData.js'
import { useAuth } from '../../hooks/useAuth.jsx'

export default function TopBar({ item }) {
  const loader = useCallback(() => health(), [])
  const { data, error } = useAsyncData(loader)
  const online = !error && data?.status === 'ok'
  const { users, currentUser, login } = useAuth()

  return (
    <header className="topbar">
      <div>
        <h1>{item?.title}</h1>
        <div className="topbar-sub">{item?.subtitle}</div>
      </div>
      <div className="topbar-meta">
        <label className="inline" style={{ gap: 6 }}>
          <span className="small muted">当前登录</span>
          <select
            className="select select-sm"
            value={currentUser?.token || ''}
            onChange={(event) => login(event.target.value)}
            style={{ minWidth: 180 }}
          >
            <option value="">未登录 (请选择)</option>
            {users.map((user) => (
              <option key={user.token} value={user.token} disabled={!user.is_active}>
                {user.name}
                {user.is_admin ? ' · 管理员' : ''}
                {user.position_name ? ` · ${user.position_name}` : ''}
                {!user.is_active ? ' (已停用)' : ''}
              </option>
            ))}
          </select>
        </label>
        {currentUser ? (
          <span className="small">
            <span style={{ color: 'var(--success)' }}>●</span> {currentUser.name}
          </span>
        ) : (
          <span className="small" style={{ color: 'var(--danger)' }}>● 未登录, 录入功能不可用</span>
        )}
        <span title={error ? error.message : `数据库: ${data?.database ?? '-'}`}>
          <span
            style={{
              display: 'inline-block',
              width: 8,
              height: 8,
              borderRadius: '50%',
              marginRight: 6,
              background: online ? 'var(--success)' : 'var(--danger)'
            }}
          />
          后端服务{online ? '正常' : '异常'}
        </span>
        <span>{data?.limit_policy ?? 'GB 3095-2012 二级标准'}</span>
        <span>{data?.timezone ?? 'Asia/Shanghai'}</span>
      </div>
    </header>
  )
}
