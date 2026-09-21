import { useCallback, useEffect, useMemo, useState } from 'react'
import { createEntries, entryContext, previewEntries } from '../../../api/measurements.js'
import { SectionCard } from '../../../components/common/Card.jsx'
import { Checkbox, Field, Input, Select } from '../../../components/common/FormField.jsx'
import { Alert, Loading } from '../../../components/common/Feedback.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { useToast } from '../../../components/common/ToastProvider.jsx'
import { useAuth } from '../../../hooks/useAuth.jsx'
import { formatNumber, toDateTimeInput } from '../../../utils/format.js'

const PERIODS = [
  { value: 'hourly', label: '小时均值' },
  { value: 'daily', label: '日均值' }
]

export default function EntryForm({ onPreview, onSubmitted }) {
  const toast = useToast()
  const { currentUser } = useAuth()

  const [context, setContext] = useState(null)
  const [contextLoading, setContextLoading] = useState(true)
  const [contextError, setContextError] = useState(null)

  const [form, setForm] = useState({
    station_id: '',
    measured_at: toDateTimeInput(),
    period: 'hourly',
    recorder_id: '',
    remark: '',
    overwrite: false
  })
  const [values, setValues] = useState({})
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(null)
  const [evaluations, setEvaluations] = useState({})

  const loadContext = useCallback(async () => {
    setContextLoading(true)
    try {
      const payload = await entryContext()
      setContext(payload)
      setContextError(null)
      setForm((prev) => ({
        ...prev,
        station_id: prev.station_id || String(payload.stations[0]?.id ?? ''),
        recorder_id: prev.recorder_id || String(payload.current_user?.id ?? '')
      }))
    } catch (error) {
      setContextError(error)
    } finally {
      setContextLoading(false)
    }
  }, [])

  useEffect(() => {
    if (currentUser) loadContext()
    else setContextLoading(false)
  }, [currentUser, loadContext])

  const stations = context?.stations ?? []
  const pollutants = context?.pollutants ?? []
  const recorders = context?.recorders ?? []
  const scope = context?.current_user?.scope

  const selectedRecorder = useMemo(
    () => recorders.find((item) => String(item.id) === String(form.recorder_id)) || null,
    [recorders, form.recorder_id]
  )
  const isProxy = Boolean(
    currentUser && selectedRecorder && selectedRecorder.id !== currentUser.id
  )

  const limitHint = useCallback(
    (pollutant) => {
      const limit = pollutant.limits?.[form.period]
      if (limit === null || limit === undefined) return '该周期未设限值, 仅记录数值'
      return `限值 ${formatNumber(limit)} ${pollutant.unit}`
    },
    [form.period]
  )

  const filled = useMemo(
    () =>
      Object.entries(values).filter(
        ([, raw]) => raw !== '' && raw !== null && raw !== undefined
      ),
    [values]
  )

  const entries = useMemo(
    () => filled.map(([pollutant, raw]) => ({ pollutant, value: Number(raw) })),
    [filled]
  )

  const setField = (key) => (event) => {
    const value = key === 'overwrite' ? event.target.checked : event.target.value
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
    setMessage(null)
  }

  const setValue = (pollutant) => (event) => {
    setValues((prev) => ({ ...prev, [pollutant]: event.target.value }))
    setErrors((prev) => ({ ...prev, [pollutant]: undefined }))
  }

  const validate = () => {
    const next = {}
    if (!form.station_id) next.station_id = '请选择监测点'
    if (!form.measured_at) next.measured_at = '请选择监测时间'
    if (filled.length === 0) next.entries = '至少填写一个因子的监测值'
    filled.forEach(([pollutant, raw]) => {
      const number = Number(raw)
      if (Number.isNaN(number)) next[pollutant] = '监测值必须是数字'
      else if (number < 0) next[pollutant] = '监测值不能为负数'
      else if (number > 10000) next[pollutant] = '监测值超出合理范围, 请检查是否录错'
    })
    setErrors(next)
    if (Object.keys(next).length) {
      setMessage('请先修正表单中标红的问题')
      return false
    }
    setMessage(null)
    return true
  }

  const buildPayload = () => ({
    station_id: Number(form.station_id),
    measured_at: form.measured_at,
    period: form.period,
    recorder_id: isProxy ? Number(form.recorder_id) : currentUser.id,
    remark: form.remark || null,
    overwrite: form.overwrite,
    entries
  })

  const runPreview = async () => {
    if (!validate()) return
    setBusy('preview')
    try {
      const result = await previewEntries({
        station_id: Number(form.station_id),
        period: form.period,
        entries
      })
      const map = {}
      result.results.forEach((item) => {
        map[item.pollutant] = item
      })
      setEvaluations(map)
      onPreview?.(result)
      if (result.summary.exceeded_count > 0) {
        toast.warning(`校验完成: ${result.summary.exceeded_count} 个因子超过限值`)
      } else {
        toast.success('校验完成: 所有因子均未超过限值')
      }
    } catch (error) {
      setErrors(error.fields || {})
      setMessage(error.message)
      toast.error(error.message)
    } finally {
      setBusy(null)
    }
  }

  const submit = async () => {
    if (!validate()) return
    setBusy('submit')
    try {
      const result = await createEntries(buildPayload())
      const map = {}
      ;(result.evaluations || []).forEach((item) => {
        map[item.pollutant] = item
      })
      setEvaluations(map)
      setValues({})
      onSubmitted?.(result)
      const written = result.summary.created_count + result.summary.updated_count
      const proxyNote = result.submitted_by?.is_proxy
        ? ` (代 ${result.submitted_by.recorder_name} 录入)`
        : ''
      if (result.summary.exceeded_count > 0) {
        toast.warning(`写入 ${written} 条数据${proxyNote}, 其中 ${result.summary.exceeded_count} 项超标已生成待标注记录`)
      } else {
        toast.success(`录入成功${proxyNote}, 共写入 ${written} 条数据`)
      }
    } catch (error) {
      setErrors(error.fields || {})
      setMessage(error.message)
      toast.error(error.status === 403 ? `越权提交已被拦截: ${error.message}` : error.message)
    } finally {
      setBusy(null)
    }
  }

  if (!currentUser) {
    return (
      <SectionCard title="监测数据录入" hint="按岗位授权录入监测点与因子数据">
        <Alert tone="warning">
          尚未选择登录人员, 请先在页面右上角选择当前登录人; 未登录时录入接口会直接拒绝提交。
        </Alert>
      </SectionCard>
    )
  }

  if (contextLoading) {
    return (
      <SectionCard title="监测数据录入">
        <Loading text="正在加载您的可录入点位与因子范围..." />
      </SectionCard>
    )
  }

  const scopeMissing = !scope
  const stationBlocked = !scopeMissing && !scope.all_stations && stations.length === 0

  return (
    <SectionCard
      title="监测数据录入"
      hint="选择监测点与监测时刻, 一次录入该时刻的各因子浓度"
      actions={<Tag tone="primary">{form.period === 'hourly' ? '小时均值' : '日均值'}</Tag>}
    >
      <div className="stack">
        {contextError ? <Alert tone="error">{contextError.message}</Alert> : null}
        {message ? <Alert tone="error">{message}</Alert> : null}

        <div className="card" style={{ boxShadow: 'none', background: 'var(--bg-muted, #f7f8fa)' }}>
          <div className="card-body">
            <div className="form-grid">
              <Field label="实际提交人 (登录人)" hint="由系统按登录身份自动带出, 不可修改">
                <Input value={`${currentUser.name}${currentUser.position_name ? ` · ${currentUser.position_name}` : ''}`} readOnly />
              </Field>
              <Field label="数据来源" hint="页面录入固定为“手工录入”, 由系统带出">
                <Input value="手工录入" readOnly />
              </Field>
              <Field label="提交时间" hint="以服务端接收时刻为准, 提交后自动记录">
                <Input value="提交时由系统自动生成" readOnly />
              </Field>
              <Field
                label="名义录入人"
                hint={isProxy ? `代录: 实际提交人为 ${currentUser.name}, 记录将标注代录关系` : '默认即本人; 选择他人即为代录'}
              >
                <Select
                  value={form.recorder_id}
                  onChange={setField('recorder_id')}
                  options={recorders.map((item) => ({
                    value: String(item.id),
                    label: item.id === currentUser.id ? `${item.name} (本人)` : item.name
                  }))}
                />
              </Field>
            </div>
            {isProxy ? (
              <Alert tone="warning" style={{ marginTop: 8 }}>
                您正在以「{selectedRecorder?.name}」的名义代录, 系统会同时记录实际提交人「{currentUser.name}」并将本条标记为代录。
              </Alert>
            ) : null}
          </div>
        </div>

        {scopeMissing ? (
          <Alert tone="error">
            您的账号当前没有已生效的录入范围 (未分配岗位、岗位停用或范围尚未到生效时间), 不能录入任何数据, 请联系管理员。
          </Alert>
        ) : null}
        {!scopeMissing && stationBlocked ? (
          <Alert tone="error">
            按当前岗位的生效口径, 您没有任何可录入的监测点。如需调整请联系管理员配置岗位范围。
          </Alert>
        ) : null}

        <div className="form-grid">
          <Field label="监测点" required error={errors.station_id} hint={scope?.all_stations ? `全部 ${context?.all_station_count ?? 0} 个点位均在范围内` : `仅限已授权的 ${stations.length} 个点位`}>
            <Select
              value={form.station_id}
              onChange={setField('station_id')}
              invalid={Boolean(errors.station_id)}
              placeholder="请选择监测点"
              options={stations.map((item) => ({
                value: String(item.id),
                label: `${item.code} ${item.name} (${item.area})`
              }))}
            />
          </Field>
          <Field label="监测时间" required error={errors.measured_at} hint="小时数据请填写整点">
            <Input
              type="datetime-local"
              value={form.measured_at}
              onChange={setField('measured_at')}
              invalid={Boolean(errors.measured_at)}
            />
          </Field>
          <Field label="数据周期" required>
            <Select value={form.period} onChange={setField('period')} options={PERIODS} />
          </Field>
          <Field label="备注">
            <Input value={form.remark} onChange={setField('remark')} placeholder="选填" />
          </Field>
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-header">
            <h3>因子浓度</h3>
            <span className="hint">
              {scope?.all_pollutants
                ? '全部因子均在您的录入范围内'
                : `仅显示已授权的 ${pollutants.length} 个因子; 留空不写入`}
            </span>
          </div>
          <div className="card-body">
            {errors.entries ? <Alert tone="error">{errors.entries}</Alert> : null}
            <div className="form-grid">
              {pollutants.map((pollutant) => {
                const evaluation = evaluations[pollutant.code]
                return (
                  <Field
                    key={pollutant.code}
                    label={`${pollutant.label} (${pollutant.unit})`}
                    error={errors[pollutant.code]}
                    hint={limitHint(pollutant)}
                  >
                    <div className="inline" style={{ flexWrap: 'nowrap' }}>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        value={values[pollutant.code] ?? ''}
                        onChange={setValue(pollutant.code)}
                        invalid={Boolean(errors[pollutant.code])}
                        placeholder="--"
                      />
                      {evaluation?.exceeded ? <Tag tone="danger">超标</Tag> : null}
                      {evaluation && !evaluation.exceeded && evaluation.applicable ? (
                        <Tag tone="success">达标</Tag>
                      ) : null}
                    </div>
                  </Field>
                )
              })}
            </div>
          </div>
        </div>

        <div>
          <Checkbox
            label="覆盖同一时刻已有数据"
            checked={form.overwrite}
            onChange={setField('overwrite')}
          />
          <div className="small muted" style={{ marginTop: 4 }}>
            勾选后重复提交将更新原记录并重新判定超标; 历史记录的录入归属仍按首次登记时的口径保留
          </div>
        </div>

        <div className="inline">
          <button
            type="button"
            className="btn"
            onClick={runPreview}
            disabled={busy !== null || scopeMissing || !form.station_id}
          >
            {busy === 'preview' ? '校验中...' : '超标校验预览'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={submit}
            disabled={busy !== null || scopeMissing || stationBlocked}
          >
            {busy === 'submit' ? '提交中...' : '提交录入'}
          </button>
          <span className="small muted">
            已填写 {filled.length} / {pollutants.length} 个因子
          </span>
        </div>
      </div>
    </SectionCard>
  )
}
