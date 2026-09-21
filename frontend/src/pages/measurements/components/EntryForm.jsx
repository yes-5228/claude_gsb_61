import { useCallback, useEffect, useMemo, useState } from 'react'
import { createEntries, entryContext, previewEntries } from '../../../api/measurements.js'
import { SectionCard } from '../../../components/common/Card.jsx'
import { Checkbox, Field, Input, Select } from '../../../components/common/FormField.jsx'
import { Alert, Loading } from '../../../components/common/Feedback.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { useToast } from '../../../components/common/ToastProvider.jsx'
import { formatNumber, toDateTimeInput } from '../../../utils/format.js'

const PERIODS = [
  { value: 'hourly', label: '小时均值' },
  { value: 'daily', label: '日均值' }
]

const POLLUTANT_LIMITS = {
  PM25: { daily: 75, hourly: null, unit: 'μg/m³', label: 'PM2.5' },
  PM10: { daily: 150, hourly: null, unit: 'μg/m³', label: 'PM10' },
  SO2: { daily: 150, hourly: 500, unit: 'μg/m³', label: 'SO₂' },
  NO2: { daily: 80, hourly: 200, unit: 'μg/m³', label: 'NO₂' },
  CO: { daily: 4, hourly: 10, unit: 'mg/m³', label: 'CO' },
  O3: { daily: 160, hourly: 200, unit: 'μg/m³', label: 'O₃' }
}

export default function EntryForm({ onPreview, onSubmitted }) {
  const toast = useToast()
  const [context, setContext] = useState(null)
  const [contextError, setContextError] = useState(null)
  const [contextLoading, setContextLoading] = useState(true)

  const [form, setForm] = useState({
    station_id: '',
    measured_at: toDateTimeInput(),
    period: 'hourly',
    on_behalf_of_id: '',
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
    setContextError(null)
    try {
      setContext(await entryContext())
    } catch (error) {
      setContextError(error)
    } finally {
      setContextLoading(false)
    }
  }, [])

  useEffect(() => {
    loadContext()
  }, [loadContext])

  const stations = context?.stations ?? []
  const allowedPollutants = context?.pollutant_codes ?? []
  const pollutants = allowedPollutants
    .map((code) => ({ code, ...POLLUTANT_LIMITS[code] }))
    .filter((item) => item.label)

  useEffect(() => {
    if (!form.station_id && stations.length) {
      setForm((prev) => ({ ...prev, station_id: String(stations[0].id) }))
    }
  }, [stations, form.station_id])

  const limitHint = useCallback(
    (pollutant) => {
      const limit = POLLUTANT_LIMITS[pollutant.code]?.[form.period]
      if (limit === null || limit === undefined) return '该周期未设限值, 仅记录数值'
      return `限值 ${formatNumber(limit)} ${pollutant.unit}`
    },
    [form.period]
  )

  const filled = useMemo(
    () => Object.entries(values).filter(([, raw]) => raw !== '' && raw !== null && raw !== undefined),
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

  const basePayload = () => ({
    station_id: Number(form.station_id),
    measured_at: form.measured_at,
    period: form.period
  })

  const runPreview = async () => {
    if (!validate()) return
    setBusy('preview')
    try {
      const result = await previewEntries({ ...basePayload(), entries })
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
      // 越权等错误: 逐字段标红 + 完整提示
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
      const result = await createEntries({
        ...basePayload(),
        remark: form.remark || null,
        on_behalf_of_id: form.on_behalf_of_id ? Number(form.on_behalf_of_id) : null,
        overwrite: form.overwrite,
        entries
      })
      const map = {}
      ;(result.evaluations || []).forEach((item) => {
        map[item.pollutant] = item
      })
      setEvaluations(map)
      setValues({})
      onSubmitted?.(result)
      const written = result.summary.created_count + result.summary.updated_count
      const who = result.submission?.is_proxy
        ? `(代 ${result.submission.recorder}, 操作人 ${result.submission.operator})`
        : ''
      if (result.summary.exceeded_count > 0) {
        toast.warning(`写入 ${written} 条数据${who}, 其中 ${result.summary.exceeded_count} 项超标已生成待标注记录`)
      } else {
        toast.success(`录入成功, 共写入 ${written} 条数据${who}`)
      }
    } catch (error) {
      setErrors(error.fields || {})
      setMessage(error.message)
      toast.error(error.message)
    } finally {
      setBusy(null)
    }
  }

  if (contextLoading) {
    return (
      <SectionCard title="监测数据录入">
        <Loading text="正在加载您岗位可录入的监测点与因子..." />
      </SectionCard>
    )
  }

  const me = context?.user
  const scope = context?.user?.scope
  const scopeText = me?.is_admin
    ? '管理员岗位, 全部监测点与因子'
    : scope
      ? `${scope.all_stations ? '全部监测点' : `${scope.station_codes.length} 个授权监测点`} · ${
          scope.all_pollutants ? '全部因子' : `${scope.pollutant_codes.length} 个授权因子`
        }`
      : ''

  return (
    <SectionCard
      title="监测数据录入"
      hint="选择监测点与监测时刻, 一次录入该时刻的各因子浓度"
      actions={<Tag tone="primary">{form.period === 'hourly' ? '小时均值' : '日均值'}</Tag>}
    >
      <div className="stack">
        {contextError ? <Alert tone="error">{contextError.message}</Alert> : null}
        {message ? <Alert tone="error">{message}</Alert> : null}

        <Alert tone="info">
          当前录入人: <strong>{me?.display_name}</strong>
          {me?.position_name ? `（${me.position_name}）` : ''} · 可录范围: {scopeText}
          <div className="small muted" style={{ marginTop: 2 }}>
            录入人、提交时间与数据来源(手工录入)由系统自动记录, 无需填写; 页面可选点位/因子已按岗位范围收窄。
          </div>
        </Alert>

        <div className="form-grid">
          <Field label="监测点" required error={errors.station_id}>
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
          {context?.can_proxy ? (
            <Field label="代录(实际录入人)" hint="留空表示本人录入; 选择后数据归属被代录人, 操作人记为您">
              <Select
                value={form.on_behalf_of_id}
                onChange={setField('on_behalf_of_id')}
                placeholder="本人录入"
                options={(context.proxy_targets || []).map((item) => ({
                  value: String(item.value),
                  label: item.label
                }))}
              />
            </Field>
          ) : (
            <Field label="代录" hint="您的岗位未开通代录权限">
              <Input value="无代录权限" disabled />
            </Field>
          )}
          <Field label="数据来源">
            <Input value="手工录入(系统自动带出)" disabled />
          </Field>
          <Field label="备注">
            <Input value={form.remark} onChange={setField('remark')} placeholder="选填" />
          </Field>
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-header">
            <h3>因子浓度</h3>
            <span className="hint">仅展示岗位授权因子, 留空的因子不会写入</span>
          </div>
          <div className="card-body">
            {errors.entries ? <Alert tone="error">{errors.entries}</Alert> : null}
            {pollutants.length === 0 ? (
              <Alert tone="warning">您当前岗位未开放任何可录入因子, 请联系管理员调整岗位范围。</Alert>
            ) : (
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
            )}
          </div>
        </div>

        <div>
          <Checkbox
            label="覆盖同一时刻已有数据"
            checked={form.overwrite}
            onChange={setField('overwrite')}
          />
          <div className="small muted" style={{ marginTop: 4 }}>
            勾选后重复提交将更新原记录并重新判定超标
          </div>
        </div>

        <div className="inline">
          <button type="button" className="btn" onClick={runPreview} disabled={busy !== null || !stations.length}>
            {busy === 'preview' ? '校验中...' : '超标校验预览'}
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={busy !== null || !stations.length}>
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
