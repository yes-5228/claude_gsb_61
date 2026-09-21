import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createPosition,
  createScope,
  createUser,
  listPositions,
  listUsers,
  updatePosition,
  updateUser
} from '../../api/admin.js'
import { listStations } from '../../api/stations.js'
import { SectionCard } from '../../components/common/Card.jsx'
import { Alert, Loading } from '../../components/common/Feedback.jsx'
import Tag from '../../components/common/Tag.jsx'
import { Checkbox, Field, Input, Select } from '../../components/common/FormField.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { useAuth } from '../../hooks/useAuth.jsx'
import { formatDateTime } from '../../utils/format.js'

const POLLUTANTS = [
  { code: 'PM25', label: 'PM2.5' },
  { code: 'PM10', label: 'PM10' },
  { code: 'SO2', label: 'SO₂' },
  { code: 'NO2', label: 'NO₂' },
  { code: 'CO', label: 'CO' },
  { code: 'O3', label: 'O₃' }
]

function nowLocalInput() {
  const d = new Date()
  d.setSeconds(0, 0)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function AdminPage() {
  const toast = useToast()
  const { currentUser } = useAuth()
  const [positions, setPositions] = useState([])
  const [users, setUsers] = useState([])
  const [stations, setStations] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [activePositionId, setActivePositionId] = useState('')

  const [newPos, setNewPos] = useState({ code: '', name: '', description: '' })
  const [scopeForm, setScopeForm] = useState({
    effective_from: nowLocalInput(),
    all_stations: false,
    all_pollutants: false,
    station_ids: [],
    pollutants: [],
    remark: ''
  })
  const [newUser, setNewUser] = useState({ username: '', name: '', position_id: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [posPayload, userPayload, stationPayload] = await Promise.all([
        listPositions(),
        listUsers(),
        listStations({ page_size: 200 })
      ])
      setPositions(posPayload.items || [])
      setUsers(userPayload.items || [])
      setStations(stationPayload.items || [])
      setActivePositionId((prev) => prev || String(posPayload.items?.[0]?.id ?? ''))
      setLoadError(null)
    } catch (error) {
      setLoadError(error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (currentUser?.is_admin) load()
  }, [currentUser, load])

  const stationMap = useMemo(() => {
    const map = new Map()
    stations.forEach((station) => map.set(station.id, station))
    return map
  }, [stations])

  if (!currentUser) {
    return (
      <SectionCard title="岗位与权限">
        <Alert tone="warning">请先在右上角选择管理员账号登录。</Alert>
      </SectionCard>
    )
  }
  if (!currentUser.is_admin) {
    return (
      <SectionCard title="岗位与权限">
        <Alert tone="error">
          当前登录人「{currentUser.name}」不是管理员, 无权查看或修改岗位与权限配置
          (后端接口同样会拦截越权请求)。
        </Alert>
      </SectionCard>
    )
  }
  if (loading) return <Loading text="正在加载岗位与人员..." />

  const activePosition = positions.find((item) => String(item.id) === String(activePositionId)) || null

  const handleCreatePosition = async () => {
    if (!newPos.code || !newPos.name) {
      toast.error('岗位编码与名称必填')
      return
    }
    setBusy(true)
    try {
      await createPosition(newPos)
      toast.success('岗位已创建')
      setNewPos({ code: '', name: '', description: '' })
      await load()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  const togglePositionActive = async (position) => {
    setBusy(true)
    try {
      await updatePosition({ id: position.id, is_active: !position.is_active })
      toast.success(position.is_active ? `岗位「${position.name}」已停用, 成员即刻失去录入权` : `岗位「${position.name}」已启用`)
      await load()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  const handleCreateScope = async () => {
    if (!activePosition) return
    setBusy(true)
    try {
      await createScope(activePosition.id, {
        effective_from: scopeForm.effective_from.replace('T', ' '),
        all_stations: scopeForm.all_stations,
        all_pollutants: scopeForm.all_pollutants,
        station_ids: scopeForm.station_ids.map(Number),
        pollutants: scopeForm.pollutants,
        remark: scopeForm.remark || null
      })
      toast.success(`新口径已登记, 自 ${scopeForm.effective_from} 起生效; 历史记录归属不变`)
      setScopeForm((prev) => ({ ...prev, remark: '' }))
      await load()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  const handleCreateUser = async () => {
    if (!newUser.username || !newUser.name) {
      toast.error('登录账号与姓名必填')
      return
    }
    setBusy(true)
    try {
      await createUser({
        ...newUser,
        position_id: newUser.position_id ? Number(newUser.position_id) : null
      })
      toast.success('人员已创建')
      setNewUser({ username: '', name: '', position_id: '' })
      await load()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  const handleUserChange = async (user, patch, successMsg) => {
    setBusy(true)
    try {
      await updateUser({ id: user.id, ...patch })
      toast.success(successMsg)
      await load()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  const toggleInList = (key, value) => {
    setScopeForm((prev) => {
      const list = prev[key]
      return {
        ...prev,
        [key]: list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
      }
    })
  }

  return (
    <div className="stack">
      {loadError ? <Alert tone="error">{loadError.message}</Alert> : null}

      <div className="grid-2">
        <SectionCard title="人员账号" hint="停用或调岗后, 其可录入范围下一次提交即立即收紧">
          <div className="stack">
            <div className="card" style={{ boxShadow: 'none' }}>
              <div className="card-header"><h3>新增人员</h3></div>
              <div className="card-body">
                <div className="form-grid">
                  <Field label="登录账号" required>
                    <Input value={newUser.username}
                      onChange={(e) => setNewUser((p) => ({ ...p, username: e.target.value }))}
                      placeholder="如 liuyang" />
                  </Field>
                  <Field label="姓名" required>
                    <Input value={newUser.name}
                      onChange={(e) => setNewUser((p) => ({ ...p, name: e.target.value }))}
                      placeholder="如 刘洋" />
                  </Field>
                  <Field label="所属岗位">
                    <Select value={newUser.position_id} placeholder="暂不分配"
                      onChange={(e) => setNewUser((p) => ({ ...p, position_id: e.target.value }))}
                      options={positions.map((p) => ({ value: String(p.id), label: p.name }))} />
                  </Field>
                </div>
                <button type="button" className="btn btn-primary btn-sm" onClick={handleCreateUser} disabled={busy}>
                  创建人员
                </button>
              </div>
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>姓名</th><th>账号</th><th>岗位</th><th>角色</th><th>状态</th><th style={{ textAlign: 'right' }}>操作</th></tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.name}</td>
                      <td className="mono small">{user.username}</td>
                      <td>
                        <Select
                          value={String(user.position_id ?? '')}
                          onChange={(e) =>
                            handleUserChange(
                              user,
                              { position_id: e.target.value ? Number(e.target.value) : null },
                              `${user.name} 调岗已生效, 后续录入按新岗位口径校验`
                            )}
                          options={[
                            { value: '', label: '无岗位' },
                            ...positions.map((p) => ({ value: String(p.id), label: p.name }))
                          ]}
                        />
                      </td>
                      <td>{user.is_admin ? <Tag tone="primary">管理员</Tag> : <Tag tone="neutral">录入员</Tag>}</td>
                      <td>{user.is_active ? <Tag tone="success">启用</Tag> : <Tag tone="neutral">已停用</Tag>}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className={`btn btn-sm ${user.is_active ? 'btn-danger' : ''}`}
                          disabled={busy || user.is_admin}
                          title={user.is_admin ? '内置管理员不可停用' : ''}
                          onClick={() =>
                            handleUserChange(
                              user,
                              { is_active: !user.is_active },
                              user.is_active ? `${user.name} 已停用, 不能再提交录入` : `${user.name} 已重新启用`
                            )}
                        >
                          {user.is_active ? '停用' : '启用'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="岗位" hint="范围调整通过登记新生效版本完成, 从不覆盖历史口径">
          <div className="stack">
            <div className="card" style={{ boxShadow: 'none' }}>
              <div className="card-header"><h3>新增岗位</h3></div>
              <div className="card-body">
                <div className="form-grid">
                  <Field label="岗位编码" required>
                    <Input value={newPos.code}
                      onChange={(e) => setNewPos((p) => ({ ...p, code: e.target.value }))}
                      placeholder="如 FUTIAN_OP" />
                  </Field>
                  <Field label="岗位名称" required>
                    <Input value={newPos.name}
                      onChange={(e) => setNewPos((p) => ({ ...p, name: e.target.value }))}
                      placeholder="如 福田区录入员" />
                  </Field>
                  <Field label="说明">
                    <Input value={newPos.description}
                      onChange={(e) => setNewPos((p) => ({ ...p, description: e.target.value }))} />
                  </Field>
                </div>
                <button type="button" className="btn btn-primary btn-sm" onClick={handleCreatePosition} disabled={busy}>
                  创建岗位
                </button>
              </div>
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>岗位</th><th>编码</th><th>状态</th><th>口径版本</th><th style={{ textAlign: 'right' }}>操作</th></tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.id} className={String(position.id) === String(activePositionId) ? 'selected-row' : ''}>
                      <td>
                        <button type="button" className="btn btn-sm"
                          onClick={() => setActivePositionId(String(position.id))}>
                          {position.name}
                        </button>
                      </td>
                      <td className="mono small">{position.code}</td>
                      <td>{position.is_active ? <Tag tone="success">启用</Tag> : <Tag tone="neutral">停用</Tag>}</td>
                      <td>{position.scopes?.length ?? 0} 版</td>
                      <td style={{ textAlign: 'right' }}>
                        <button type="button" className={`btn btn-sm ${position.is_active ? 'btn-danger' : ''}`}
                          disabled={busy || position.code === 'ADMIN'}
                          title={position.code === 'ADMIN' ? '内置管理员岗位不可停用' : ''}
                          onClick={() => togglePositionActive(position)}>
                          {position.is_active ? '停用岗位' : '启用岗位'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </SectionCard>
      </div>

      {activePosition ? (
        <SectionCard
          title={`范围口径 · ${activePosition.name}`}
          hint="新版本自生效时间起仅影响此后的录入; 历史监测数据仍按登记当时的版本归属"
        >
          <div className="grid-2">
            <div>
              <h3>登记新生效版本</h3>
              <div className="stack">
                <Field label="生效时间" required hint="早于该时间的录入不受影响">
                  <Input type="datetime-local"
                    value={scopeForm.effective_from.replace(' ', 'T')}
                    onChange={(e) =>
                      setScopeForm((p) => ({ ...p, effective_from: e.target.value.replace('T', ' ') }))} />
                </Field>
                <Checkbox label="全部监测点 (勾选后无需逐项选择)" checked={scopeForm.all_stations}
                  onChange={() => setScopeForm((p) => ({ ...p, all_stations: !p.all_stations }))} />
                {!scopeForm.all_stations ? (
                  <div className="checkbox-group card" style={{ boxShadow: 'none' }}>
                    <div className="card-body">
                      <div className="small muted" style={{ marginBottom: 6 }}>可录入监测点 ({scopeForm.station_ids.length})</div>
                      <div className="form-grid">
                        {stations.map((station) => (
                          <label key={station.id} className="checkbox">
                            <input type="checkbox"
                              checked={scopeForm.station_ids.includes(station.id)}
                              onChange={() => toggleInList('station_ids', station.id)} />
                            <span className="small">{station.code} {station.name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
                <Checkbox label="全部监测因子" checked={scopeForm.all_pollutants}
                  onChange={() => setScopeForm((p) => ({ ...p, all_pollutants: !p.all_pollutants }))} />
                {!scopeForm.all_pollutants ? (
                  <div className="inline">
                    {POLLUTANTS.map((pollutant) => (
                      <label key={pollutant.code} className="checkbox">
                        <input type="checkbox"
                          checked={scopeForm.pollutants.includes(pollutant.code)}
                          onChange={() => toggleInList('pollutants', pollutant.code)} />
                        <span className="small">{pollutant.label}</span>
                      </label>
                    ))}
                  </div>
                ) : null}
                <Field label="调整说明">
                  <Input value={scopeForm.remark}
                    onChange={(e) => setScopeForm((p) => ({ ...p, remark: e.target.value }))}
                    placeholder="如: 新增宝安片区点位 / 收窄至颗粒物因子" />
                </Field>
                <div>
                  <button type="button" className="btn btn-primary" onClick={handleCreateScope} disabled={busy}>
                    登记新生效口径
                  </button>
                </div>
              </div>
            </div>

            <div>
              <h3>历史口径版本 (按生效时间倒序)</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr><th>生效时间</th><th>点位范围</th><th>因子范围</th><th>说明</th></tr>
                  </thead>
                  <tbody>
                    {(activePosition.scopes || []).map((scope, index) => (
                      <tr key={scope.id}>
                        <td className="cell-nowrap">
                          {formatDateTime(scope.effective_from)}
                          {index === 0 ? <div><Tag tone="success">当前生效</Tag></div> : null}
                        </td>
                        <td className="small">
                          {scope.all_stations
                            ? '全部点位'
                            : scope.station_ids
                                .map((id) => stationMap.get(id)?.name || `#${id}`)
                                .join('、') || <span className="muted">无</span>}
                        </td>
                        <td className="small">
                          {scope.all_pollutants ? '全部因子' : (scope.pollutants || []).join('、') || <span className="muted">无</span>}
                        </td>
                        <td className="small muted">{scope.remark || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </SectionCard>
      ) : null}
    </div>
  )
}
