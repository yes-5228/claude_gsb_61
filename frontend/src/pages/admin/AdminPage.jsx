import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  addScopeVersion,
  createUser,
  listPositions,
  listUsers,
  updateUser
} from '../../api/admin.js'
import { stationOptions } from '../../api/stations.js'
import { pollutants as fetchPollutants } from '../../api/meta.js'
import { SectionCard } from '../../components/common/Card.jsx'
import { Checkbox, Field, Input, Select } from '../../components/common/FormField.jsx'
import { Alert, Loading } from '../../components/common/Feedback.jsx'
import Modal from '../../components/common/Modal.jsx'
import Tag from '../../components/common/Tag.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { formatDateTime } from '../../utils/format.js'

function ScopeSummary({ scope }) {
  if (!scope) return <Tag tone="neutral">未配置范围(暂不可录)</Tag>
  const stationText = scope.all_stations ? '全部点位' : `${scope.station_codes.length} 个点位`
  const factorText = scope.all_pollutants ? '全部因子' : `${scope.pollutant_codes.length} 个因子`
  return (
    <span className="small muted">
      {stationText} · {factorText}
    </span>
  )
}

export default function AdminPage() {
  const toast = useToast()
  const [users, setUsers] = useState([])
  const [positions, setPositions] = useState([])
  const [stations, setStations] = useState([])
  const [pollutants, setPollutants] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [userModal, setUserModal] = useState(null) // {mode:'create'} | user object
  const [scopeTarget, setScopeTarget] = useState(null) // position

  const stationName = useCallback(
    (code) => {
      const found = stations.find((item) => item.code === code)
      return found ? `${found.code} ${found.name}` : code
    },
    [stations]
  )

  const loadAll = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [userData, positionData, stationData, pollutantData] = await Promise.all([
        listUsers(),
        listPositions(),
        stationOptions(),
        fetchPollutants()
      ])
      setUsers(userData.items)
      setPositions(positionData.items)
      setStations(stationData.items || [])
      setPollutants(pollutantData.items || [])
    } catch (error) {
      setLoadError(error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const positionOptions = useMemo(
    () => positions.map((item) => ({ value: String(item.id), label: `${item.name}(${item.code})` })),
    [positions]
  )

  if (loading) return <Loading text="正在加载人员与岗位..." />
  if (loadError) return <Alert tone="error">{loadError.message}</Alert>

  return (
    <div className="stack">
      <SectionCard
        title="人员账号"
        hint="停用或调岗后, 该账号的可录入范围立即收紧, 已登录会话同样实时生效"
        actions={
          <button className="btn btn-primary btn-sm" onClick={() => setUserModal({ mode: 'create' })}>
            + 新增账号
          </button>
        }
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>账号</th>
                <th>姓名(录入人)</th>
                <th>岗位</th>
                <th>当前可录入范围</th>
                <th>代录</th>
                <th>状态</th>
                <th>最近登录</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.display_name}</td>
                  <td>{user.position_name}</td>
                  <td>
                    {user.is_admin ? (
                      <Tag tone="primary">全量(管理员)</Tag>
                    ) : (
                      <ScopeSummary scope={user.scope} />
                    )}
                  </td>
                  <td>{user.can_proxy ? <Tag tone="info">可代录</Tag> : <span className="muted">-</span>}</td>
                  <td>
                    {user.active ? <Tag tone="success">启用</Tag> : <Tag tone="neutral">停用</Tag>}
                  </td>
                  <td className="small muted">{formatDateTime(user.last_login_at)}</td>
                  <td>
                    <button className="btn btn-sm" onClick={() => setUserModal({ ...user, mode: 'edit' })}>
                      编辑/调岗
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard
        title="岗位与录入范围"
        hint="范围调整以新版本生效, 需指定生效时间; 仅影响该时间之后的录入, 历史数据按登记当时口径保留"
      >
        <div className="stack-lg">
          {positions.map((position) => (
            <div className="card" key={position.id} style={{ boxShadow: 'none' }}>
              <div className="card-body tight">
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <strong>{position.name}</strong>
                    <span className="small muted" style={{ marginLeft: 8 }}>
                      {position.code} · {position.user_count} 人
                    </span>
                    {position.is_admin ? <Tag tone="primary" style={{ marginLeft: 8 }}>管理员</Tag> : null}
                    {position.can_proxy ? <Tag tone="info" style={{ marginLeft: 8 }}>可代录</Tag> : null}
                  </div>
                  {position.is_admin ? null : (
                    <button className="btn btn-sm" onClick={() => setScopeTarget(position)}>
                      调整范围(设生效时间)
                    </button>
                  )}
                </div>
                {position.remark ? <div className="small muted" style={{ marginTop: 6 }}>{position.remark}</div> : null}

                {position.is_admin ? null : (
                  <div className="scope-versions">
                    <div className="small muted" style={{ margin: '8px 0 4px' }}>范围版本(按生效时间):</div>
                    {position.scope_versions.length === 0 ? (
                      <div className="small"><Tag tone="warning">尚未配置任何版本, 该岗位当前无法录入</Tag></div>
                    ) : (
                      <table className="table table-compact">
                        <thead>
                          <tr>
                            <th>生效时间</th>
                            <th>监测点</th>
                            <th>因子</th>
                            <th>说明</th>
                          </tr>
                        </thead>
                        <tbody>
                          {position.scope_versions.map((version, index) => (
                            <tr key={version.id}>
                              <td className="cell-nowrap">
                                {formatDateTime(version.effective_from)}
                                {index === 0 && new Date(version.effective_from) > new Date() ? (
                                  <Tag tone="warning" style={{ marginLeft: 6 }}>待生效</Tag>
                                ) : null}
                                {index === 0 && new Date(version.effective_from) <= new Date() ? (
                                  <Tag tone="success" style={{ marginLeft: 6 }}>当前生效</Tag>
                                ) : null}
                              </td>
                              <td>
                                {version.all_stations
                                  ? '全部点位'
                                  : version.station_codes.map(stationName).join('、')}
                              </td>
                              <td>
                                {version.all_pollutants
                                  ? '全部因子'
                                  : version.pollutant_codes
                                      .map((code) => pollutants.find((p) => p.code === code)?.label || code)
                                      .join('、')}
                              </td>
                              <td className="small muted">{version.remark || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      {userModal ? (
        <UserModal
          mode={userModal.mode}
          user={userModal.mode === 'edit' ? userModal : null}
          positionOptions={positionOptions}
          onClose={() => setUserModal(null)}
          onSaved={() => {
            setUserModal(null)
            loadAll()
            toast.success('账号信息已保存, 权限变更即时生效')
          }}
        />
      ) : null}

      {scopeTarget ? (
        <ScopeModal
          position={scopeTarget}
          stations={stations}
          pollutants={pollutants}
          onClose={() => setScopeTarget(null)}
          onSaved={() => {
            setScopeTarget(null)
            loadAll()
            toast.success('范围新版本已登记, 将自设定的生效时间起适用')
          }}
        />
      ) : null}
    </div>
  )
}

function UserModal({ mode, user, positionOptions, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({
    username: user?.username || '',
    display_name: user?.display_name || '',
    position_id: user ? String(user.position_id) : positionOptions[0]?.value || '',
    active: user ? user.active : true,
    password: '',
    remark: user?.remark || ''
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const set = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = {
        display_name: form.display_name,
        position_id: Number(form.position_id),
        active: form.active,
        remark: form.remark || null
      }
      if (mode === 'create') {
        await createUser({ ...payload, username: form.username.trim(), password: form.password })
      } else {
        if (form.password) payload.password = form.password
        await updateUser(user.id, payload)
      }
      onSaved()
    } catch (err) {
      setError(err)
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title={mode === 'create' ? '新增账号' : `编辑账号 · ${user.username}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? '保存中...' : '保存'}
          </button>
        </>
      }
    >
      <div className="stack">
        {error ? <Alert tone="error">{error.message}</Alert> : null}
        <div className="form-grid">
          {mode === 'create' ? (
            <Field label="登录账号" required>
              <Input value={form.username} onChange={set('username')} placeholder="如: lisi" />
            </Field>
          ) : null}
          <Field label="姓名(录入人)" required>
            <Input value={form.display_name} onChange={set('display_name')} />
          </Field>
          <Field label="所属岗位" required>
            <Select value={form.position_id} onChange={set('position_id')} options={positionOptions} />
          </Field>
          <Field label={mode === 'create' ? '初始密码(≥6位)' : '重置密码(留空则不改)'} required={mode === 'create'}>
            <Input type="password" value={form.password} onChange={set('password')} placeholder="至少 6 位" />
          </Field>
          <Field label="备注">
            <Input value={form.remark} onChange={set('remark')} />
          </Field>
        </div>
        <Checkbox label="账号启用(取消勾选立即停用, 其录入权限立即收回)" checked={form.active} onChange={set('active')} />
      </div>
    </Modal>
  )
}

function ScopeModal({ position, stations, pollutants, onClose, onSaved }) {
  const nowLocal = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
  const [effectiveFrom, setEffectiveFrom] = useState(nowLocal)
  const [allStations, setAllStations] = useState(true)
  const [allPollutants, setAllPollutants] = useState(true)
  const [stationCodes, setStationCodes] = useState([])
  const [pollutantCodes, setPollutantCodes] = useState([])
  const [remark, setRemark] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const toast = useToast()

  const toggleIn = (list, setList, code) => () => {
    setList(list.includes(code) ? list.filter((item) => item !== code) : [...list, code])
  }

  const save = async () => {
    if (!allStations && stationCodes.length === 0) {
      setError({ message: '限制点位时至少勾选一个监测点' })
      return
    }
    if (!allPollutants && pollutantCodes.length === 0) {
      setError({ message: '限制因子时至少勾选一个因子' })
      return
    }
    setBusy(true)
    setError(null)
    try {
      await addScopeVersion(position.id, {
        effective_from: effectiveFrom.replace('T', ' '),
        all_stations: allStations,
        all_pollutants: allPollutants,
        station_codes: stationCodes,
        pollutant_codes: pollutantCodes,
        remark: remark || null
      })
      onSaved()
    } catch (err) {
      setError(err)
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      width="wide"
      title={`调整录入范围 · ${position.name}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? '提交中...' : '登记新版本'}
          </button>
        </>
      }
    >
      <div className="stack">
        <Alert tone="info">
          调整将生成一个新版本, 自「生效时间」起适用于此后的录入; 早于该时间已登记的数据仍按旧口径归属, 不会被改写。
        </Alert>
        {error ? <Alert tone="error">{error.message}</Alert> : null}

        <Field label="生效时间" required hint="可设为未来时间(到期自动切换), 也可设为当前/过去时间立即生效">
          <Input type="datetime-local" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
        </Field>

        <div>
          <div className="field-label">可录入监测点</div>
          <Checkbox label="全部监测点" checked={allStations}
            onChange={(e) => setAllStations(e.target.checked)} />
          {allStations ? null : (
            <div className="check-grid">
              {stations.map((station) => (
                <label className="checkbox" key={station.code}>
                  <input type="checkbox" checked={stationCodes.includes(station.code)}
                    onChange={toggleIn(stationCodes, setStationCodes, station.code)} />
                  <span>{station.code} {station.name}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="field-label">可录入监测因子</div>
          <Checkbox label="全部监测因子" checked={allPollutants}
            onChange={(e) => setAllPollutants(e.target.checked)} />
          {allPollutants ? null : (
            <div className="check-grid">
              {pollutants.map((pollutant) => (
                <label className="checkbox" key={pollutant.code}>
                  <input type="checkbox" checked={pollutantCodes.includes(pollutant.code)}
                    onChange={toggleIn(pollutantCodes, setPollutantCodes, pollutant.code)} />
                  <span>{pollutant.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <Field label="版本说明">
          <Input value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="如: 新增宝安片区录入职责" />
        </Field>
      </div>
    </Modal>
  )
}
