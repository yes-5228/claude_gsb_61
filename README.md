# 空气监测点数据录入系统

面向空气质量监测业务的**监测点台账 + 监测数据录入 + 超标记录标注 + 数据查询**一体化系统。
后端使用 Flask + SQLAlchemy 以蓝图/服务分层组织, 前端使用 React + Vite 按业务模块拆分页面,
超标判定严格依据 **GB 3095-2012《环境空气质量标准》二级浓度限值** 自动完成。

## 功能模块

| 模块 | 路由 | 主要能力 |
| --- | --- | --- |
| 运行概览 | `/overview` | 监测点规模、数据总量、超标与待标注统计、近 7 日数据量趋势、待办超标列表 |
| 监测点台账 | `/stations` | 台账增删改查、区域/类型/状态筛选、点位详情与分因子统计、级联清理关联数据 |
| 监测数据录入 | `/measurements` | 按“监测点 + 时刻 + 周期”成组录入多因子浓度、超标校验预览、重复数据覆盖、录入结果回执 |
| 超标记录标注 | `/exceedances` | 超标自动建单、单条/批量标注(确认 / 忽略 / 重置)、等级人工修正、标注留痕与统计 |
| 数据查询 | `/query` | 多条件组合检索、聚合统计(按因子/站点/区域/日/月等)、分页浏览、CSV 导出 |

设计要点:

- **超标自动判定**: 数据写入时即按“因子 + 数据周期”取用限值, 计算超标倍数并分级, 同步生成待标注超标记录; 修正数据后超标记录自动更新或撤销。
- **岗位录入权限**: 不同岗位可录入的**监测点范围与因子范围**不同; 范围以“带生效时间的口径版本”登记, 调整只影响此后录入, 历史数据按登记当时口径归属。停用/调岗实时生效, 权限判定在服务端逐次现查, 绕过页面直接提交接口同样被拦截。
- **录入审计自动留痕**: 实际提交人(登录人)、提交时间、数据来源全部由服务端带出, 请求体无法伪造; 选择他人作为名义录入人即**代录**, 自动标注实际提交人。
- **业务规则集中在后端**: 限值、分级规则与权限校验位于 `backend/app/domain/`、`backend/app/services/`, 前端仅做展示与前置校验, 避免规则分叉。
- **模块化组织**: 后端按 `api / services / models / domain / utils` 分层; 前端每个业务模块独占目录, 公共能力沉淀在 `components/`、`hooks/`、`api/`。

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 后端 | Python 3.12 · Flask 3 · Flask-SQLAlchemy 3 · Flask-CORS · Gunicorn |
| 数据库 | SQLite(默认, 零依赖) / PostgreSQL 16(可选, compose 覆盖文件) |
| 前端 | React 18 · React Router 6 · Vite 7 · Axios · 原生 CSS(设计令牌 + 组件类) |
| 部署 | Docker 多阶段构建 · Nginx 静态托管与 `/api` 反向代理 · docker compose |
| 测试 | Pytest(66 个后端用例: 接口 + 领域规则 + 岗位录入权限) |

## 目录结构

```text
.
├── backend/                     # Flask 后端
│   ├── app/
│   │   ├── __init__.py          # 应用工厂 create_app
│   │   ├── config.py            # 多环境配置 (development/production/testing)
│   │   ├── extensions.py        # db / cors 单例, SQLite 外键开关
│   │   ├── errors.py            # 统一异常与 JSON 错误响应
│   │   ├── commands.py          # flask init-db / seed / reset-db / stats
│   │   ├── seed.py              # 演示数据生成与启动引导
│   │   ├── domain/              # 业务规则: 因子限值、枚举、超标分级
│   │   ├── models/              # Station / Measurement / Exceedance
│   │   ├── services/            # 台账、录入、标注、查询统计业务逻辑
│   │   ├── api/                 # 蓝图: meta / stations / measurements / exceedances / query
│   │   └── utils/               # 校验器、分页、CSV 导出
│   ├── tests/                   # Pytest 用例
│   ├── Dockerfile · docker-entrypoint.sh · requirements*.txt
│   └── run.py · wsgi.py
├── frontend/                    # React 前端
│   ├── src/
│   │   ├── api/                 # 按模块拆分的接口封装 + axios 客户端
│   │   ├── components/          # layout(侧边栏/顶栏) 与 common(表格/分页/弹窗/表单等)
│   │   ├── constants/           # 路由、标签与色板映射
│   │   ├── hooks/               # useListQuery / useAsyncData / useOptions
│   │   ├── pages/               # overview / stations / measurements / exceedances / query
│   │   ├── styles/global.css    # 设计令牌与公共样式
│   │   └── utils/               # 时间/数值格式化、下载
│   ├── Dockerfile · nginx.conf · vite.config.js
│   └── package.json
├── docker-compose.yml           # 默认编排(SQLite 卷)
└── docker-compose.postgres.yml  # 可选覆盖文件(PostgreSQL)
```

## 快速开始

### 方式一: Docker Compose (推荐)

```bash
docker compose up -d --build
```

启动完成后:

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 前端 | http://localhost:8080 | Nginx 托管, `/api` 反向代理到后端 |
| 后端 | http://localhost:5000/api/meta/health | 健康检查 |

首次启动会自动建表并写入演示数据(8 个监测点 / 1200 条监测数据 / 52 条超标记录), 可通过环境变量 `SEED_DEMO=false` 关闭。

```bash
docker compose ps          # 查看容器与健康状态
docker compose logs -f backend
docker compose down        # 停止(保留数据卷)
docker compose down -v     # 停止并删除数据卷
```

### 方式二: 本地开发

后端(默认使用 SQLite, 无需额外依赖):

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m flask --app wsgi init-db      # 建表
python -m flask --app wsgi seed         # 可选: 写入演示数据
python run.py                           # http://127.0.0.1:5000
```

前端(Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:5000`):

```bash
cd frontend
npm install
npm run dev                             # http://127.0.0.1:5173
```

> 若后端不在默认地址, 通过 `VITE_PROXY_TARGET=http://host:port npm run dev` 指定, 或复制 `.env.example` 为 `.env` 后修改。

### 方式三: 使用 PostgreSQL

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

覆盖文件会新增 `postgres:16-alpine` 服务并把后端 `DATABASE_URL` 指向它; 后端容器会等待数据库健康检查通过后再建表初始化。

## 超标判定规则

判定逻辑位于 `backend/app/domain/exceedance_rules.py`, 限值定义位于 `backend/app/domain/standards.py`。

**GB 3095-2012 二级浓度限值**

| 监测因子 | 1 小时平均 | 24 小时平均 | 单位 |
| --- | --- | --- | --- |
| PM2.5 | 不设限值(仅记录) | 75 | μg/m³ |
| PM10 | 不设限值(仅记录) | 150 | μg/m³ |
| SO₂ | 500 | 150 | μg/m³ |
| NO₂ | 200 | 80 | μg/m³ |
| CO | 10 | 4 | mg/m³ |
| O₃ | 200 | 160 | μg/m³ |

- **判定**: `监测值 > 限值` 即判为超标, 记录限值快照与原值, 避免限值调整后历史数据失真。
- **分级**: 超标倍数 = 监测值 / 限值; `1.0 ~ 1.5 倍` 为轻度超标, `1.5 ~ 2.0 倍` 为中度超标, `≥ 2.0 倍` 为重度超标。
- **无 1 小时限值的因子**(PM2.5、PM10 小时值)仅记录数值, 不参与超标判定, 避免误报。
- **标注状态**: `待标注(pending)` 由系统自动创建, 人工标注为 `已确认(confirmed)` 或 `已忽略(ignored)`; 确认与忽略都必须填写标注说明, 用于后续追溯。

## API 概览

统一前缀 `/api`, 成功直接返回数据对象; 失败返回 `{"error": {"code": "...", "message": "...", "fields": {...}}}`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/meta/health` | 健康检查(数据库连通性、时区、限值标准) |
| GET | `/api/meta/pollutants` | 监测因子清单与限值 |
| GET | `/api/meta/options` | 枚举选项(监测点、区域、状态、类型等) |
| GET | `/api/meta/overview` | 首页概览聚合数据 |
| GET | `/api/auth/me` | 当前登录人及其生效中的可录入范围 |
| GET | `/api/auth/users` | 人员清单(顶栏切换登录人 / 选择代录对象) |
| GET/POST | `/api/admin/positions` | 【管理员】岗位查询 / 新增 |
| PUT | `/api/admin/positions/{id}` | 【管理员】岗位更新(启用/停用) |
| GET/POST | `/api/admin/positions/{id}/scopes` | 【管理员】口径版本列表 / 登记新生效范围(带生效时间) |
| GET/POST | `/api/admin/users` | 【管理员】人员查询 / 新增 |
| PUT | `/api/admin/users/{id}` | 【管理员】调岗 / 停用(立即生效) |
| GET/POST | `/api/stations` | 台账分页查询 / 新增 |
| GET/PUT/DELETE | `/api/stations/{id}` | 台账详情(含分因子统计) / 更新 / 删除(级联) |
| GET | `/api/stations/options` | 下拉选项(监测点、区域) |
| GET | `/api/stations/summary` | 台账规模统计 |
| GET | `/api/measurements` | 监测数据分页查询(含筛选汇总) |
| POST | `/api/measurements/entries` | **成组录入**: 需登录, 按岗位口径鉴权(点位+因子) |
| POST | `/api/measurements/preview` | 超标校验预览(不写库, 同样鉴权) |
| GET | `/api/measurements/entry-context` | 当前登录人的可录入点位/因子/代录对象 |
| DELETE | `/api/measurements/{id}` | 删除监测数据 |
| GET | `/api/measurements/export` | 按条件导出 CSV(含名义录入人/代录标记/提交时间) |
| GET | `/api/exceedances` | 超标记录查询(含筛选统计) |
| GET | `/api/exceedances/{id}` | 超标记录详情(含关联监测数据) |
| PATCH | `/api/exceedances/{id}` | 单条标注 |
| POST | `/api/exceedances/annotations` | 批量标注 |
| GET | `/api/exceedances/summary` | 超标统计(状态/等级/高发因子/站点排名) |
| GET | `/api/query/measurements` | 高级条件检索 |
| GET | `/api/query/statistics` | 聚合统计(`group_by` + `metric`) |
| GET | `/api/query/export` | 查询结果导出 CSV |

### 登录身份与录入权限

- 前端在顶栏选择登录人员后, 后续请求自动携带 `X-Operator-Token: <token>` 头;
  未携带或令牌无效时, 录入/预览及管理接口返回 `401 UNAUTHORIZED`。
- `POST /api/measurements/entries` 与 `/preview` 每次都按**当前登录账号 → 所属岗位 →
  当前时刻已生效的口径版本**实时校验, 不做缓存:
  - 账号停用、岗位停用 → `403 PERMISSION_DENIED`(下一次提交立即收紧);
  - 调岗 → 立即按新岗位口径校验;
  - 监测点不在范围内 → 403, 提示具体点位; 因子不在范围内 → 403, 提示具体因子。
- **录入人 / 提交时间 / 数据来源由服务端自动带出**, 请求体里的 `recorder`、`data_source` 一律忽略;
  页面手工录入的 `data_source` 固定为 `manual`。
- 请求体传 `recorder_id` 指定他人即**代录**: `recorder` 落名义录入人,
  `operator_name` 落实际提交登录人, `is_proxy=true`; 不传则名义录入人即本人。
- 范围调整通过 `POST /api/admin/positions/{id}/scopes` 登记**新版本 + 生效时间**完成,
  旧版本保留; 监测数据写入时快照 `position_id / scope_id`, 覆盖更新也不改变首次归属。

`POST /api/measurements/entries` 请求示例 (实际提交人、提交时间、数据来源无需也无法传入):

```json
{
  "station_id": 1,
  "measured_at": "2026-09-14 10:00",
  "period": "hourly",
  "recorder_id": 5,
  "remark": "在线设备人工比对; 李静代赵宇录入",
  "overwrite": false,
  "entries": [
    { "pollutant": "PM25", "value": 82.5 },
    { "pollutant": "SO2", "value": 640 },
    { "pollutant": "CO", "value": 1.4 }
  ]
}
```

响应中 `submitted_by` 回传本次提交的审计归属, 越权时返回 `403` 并在 `message` 中说明原因:

```json
{
  "created": [ "..." ],
  "updated": [],
  "exceedances": [ { "pollutant": "SO2", "level": "moderate", "exceed_ratio": 1.28 } ],
  "duplicates": [],
  "summary": { "created_count": 3, "updated_count": 0, "exceeded_count": 1, "duplicate_count": 0 }
}
```

## 数据模型

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `positions` | `code` `name` `is_active` | 岗位 |
| `position_scopes` | `position_id` `effective_from` `all_stations` `all_pollutants` | 岗位录入口径版本, 同岗位可多版, 按提交时刻取已生效的最新版 |
| `scope_stations` / `scope_pollutants` | `scope_id` `station_id` / `pollutant` | 每版口径允许的点位与因子 |
| `users` | `username` `name` `token` `is_active` `is_admin` `position_id` | 录入账号; 停用/调岗实时影响可录入范围 |
| `stations` | `code`(唯一) `name` `area` `station_type` `status` `longitude/latitude` `installed_at` | 监测点台账 |
| `measurements` | `station_id` `pollutant` `period` `value` `limit_value` `exceed_ratio` `is_exceeded` `measured_at` `data_source` `recorder`; 审计列 `operator_id/operator_name`(实际提交人) `recorder_id`(名义录入人) `is_proxy`(代录) `submitted_at`(提交时间) `position_id/scope_id`(登记当时口径快照) | 监测数据; `(station_id, pollutant, period, measured_at)` 唯一 |
| `exceedances` | `measurement_id`(唯一) `status` `level` `note` `annotator` `annotated_at` | 超标记录与人工标注 |

删除监测点会级联清理其监测数据与超标记录; 删除监测数据会同时删除对应超标记录。

> 升级注意: 本次新增了岗位/人员表与监测数据审计列, 旧的本地 SQLite 库需要重置
> (`flask reset-db` 或删除 `backend/instance/air_monitor.db` 后重启)。
> 重置后种子数据包含演示账号, 令牌形如 `demo-token-<username>`(如 `demo-token-lijing`、
> `demo-token-admin`), 可在顶栏直接切换。

## 配置项

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FLASK_ENV` | `development` | `development` / `production` / `testing` |
| `DATABASE_URL` | SQLite(`backend/instance/air_monitor.db`) | 如 `postgresql+psycopg2://user:pass@host:5432/db` |
| `CORS_ORIGINS` | `*` | 允许的前端来源, 逗号分隔 |
| `TIMEZONE` | `Asia/Shanghai` | 展示时区 |
| `AUTO_INIT_DB` / `AUTO_SEED` | `true`(开发) | 启动时自动建表 / 写入演示数据 |
| `SEED_DEMO` | `true` | Docker 容器启动时是否写入演示数据 |
| `GUNICORN_WORKERS` | `2` | 生产容器 worker 数量 |
| `VITE_API_BASE` | `/api` | 前端接口前缀 |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:5000` | 开发代理的后端地址 |

## 测试与校验

```bash
cd backend
python -m pytest -q          # 66 个用例: 台账/录入与超标判定、岗位权限(越权/代录/口径生效/停用调岗)、标注、查询导出、元数据

cd frontend
npm run build                # 生产构建校验
```

健康检查与常用命令:

```bash
curl http://localhost:5000/api/meta/health
python -m flask --app wsgi stats      # 查看监测点/数据/超标记录数量
python -m flask --app wsgi reset-db   # 重置数据库并重建演示数据
```

## 常见问题

- **端口被占用**: 后端改 `PORT=5001 python run.py`(同时调整 `VITE_PROXY_TARGET`), 或修改 compose 的端口映射。
- **想清空演示数据**: `python -m flask --app wsgi reset-db --empty`, 或 `docker compose down -v` 后重新启动。
- **SQLite 文件位置**: 本地开发为 `backend/instance/air_monitor.db`; Docker 部署为数据卷 `air-monitor-data` 中的 `/data/air_monitor.db`。
- **前端页面 404 / 刷新报错**: Nginx 已配置 SPA 回退(`try_files ... /index.html`), 自定义部署时需保留该配置。
- **时区**: 系统按“本地墙钟时间”存储与展示监测时间, 部署时请保持后端 `TIMEZONE` 与业务所在地一致。
