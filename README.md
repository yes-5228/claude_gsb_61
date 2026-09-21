# 空气监测点数据录入系统

面向空气质量监测业务的**监测点台账 + 监测数据录入 + 超标记录标注 + 数据查询**一体化系统。
后端使用 Flask + SQLAlchemy 以蓝图/服务分层组织, 前端使用 React + Vite 按业务模块拆分页面,
超标判定严格依据 **GB 3095-2012《环境空气质量标准》二级浓度限值** 自动完成。

## 功能模块

| 模块 | 路由 | 主要能力 |
| --- | --- | --- |
| 登录 | `/login` | 账号密码登录, 签名令牌会话, 停用/调岗实时失效 |
| 运行概览 | `/overview` | 监测点规模、数据总量、超标与待标注统计、近 7 日数据量趋势、待办超标列表 |
| 监测点台账 | `/stations` | 台账增删改查、区域/类型/状态筛选、点位详情与分因子统计、级联清理关联数据 |
| 监测数据录入 | `/measurements` | 按“监测点 + 时刻 + 周期”成组录入多因子浓度、**按岗位范围收窄并强校验**、超标校验预览、重复数据覆盖、录入结果回执 |
| 超标记录标注 | `/exceedances` | 超标自动建单、单条/批量标注(确认 / 忽略 / 重置)、等级人工修正、标注留痕与统计 |
| 数据查询 | `/query` | 多条件组合检索、聚合统计(按因子/站点/区域/日/月等)、分页浏览、CSV 导出 |
| 岗位与人员 | `/admin`(管理员) | 岗位维护、账号新增/停用/调岗、**带生效时间的点位+因子录入范围版本管理** |

设计要点:

- **岗位分级录入**: 每个岗位绑定“可录入监测点 + 可录入因子”的**范围版本**, 录入时在服务层实时校验; 越权提交(含绕过页面直连接口、伪造录入人/来源)一律 403 拦截并返回可读原因。
- **范围调整带生效时间**: 一次调整生成一个新版本, 仅适用于生效时间之后的录入; 每条数据快照登记当时的岗位与范围版本, **历史归属口径不因后续调整而改变**。
- **停用/调岗立即收紧**: 授权每次实时查库, 账号或岗位停用、人员调岗后, 既有登录会话的可录入范围立即变化, 无需等待令牌过期。
- **录入痕迹自动带出**: 录入人、实际操作人、提交时间、数据来源(手工录入)均由服务端依据登录账号写入, 不信任请求体; 支持**代录**(数据归属被代录人, 另记实际操作人)。
- **超标自动判定**: 数据写入时即按“因子 + 数据周期”取用限值, 计算超标倍数并分级, 同步生成待标注超标记录; 修正数据后超标记录自动更新或撤销。
- **业务规则集中在后端**: 限值与分级规则位于 `backend/app/domain/`, 权限判定位于 `backend/app/services/auth_service.py`, 前端仅做展示与前置收窄, 避免规则分叉。
- **模块化组织**: 后端按 `api / services / models / domain / utils` 分层; 前端每个业务模块独占目录, 公共能力沉淀在 `components/`、`hooks/`、`api/`。

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 后端 | Python 3.12 · Flask 3 · Flask-SQLAlchemy 3 · Flask-CORS · Gunicorn |
| 数据库 | SQLite(默认, 零依赖) / PostgreSQL 16(可选, compose 覆盖文件) |
| 前端 | React 18 · React Router 6 · Vite 7 · Axios · 原生 CSS(设计令牌 + 组件类) |
| 部署 | Docker 多阶段构建 · Nginx 静态托管与 `/api` 反向代理 · docker compose |
| 测试 | Pytest(64 个后端用例: 接口 + 领域规则 + 岗位授权) |

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

首次启动会自动建表并写入演示数据(8 个监测点 / 1200 条监测数据 / 约 50 条超标记录 / 6 个账号与 5 个岗位), 可通过环境变量 `SEED_DEMO=false` 关闭。

**演示账号(初始密码均为 `air123456`)**:

| 账号 | 姓名 / 岗位 | 可录入范围 |
| --- | --- | --- |
| `admin` | 系统管理员 | 全部点位/因子, 可管理人员与范围、可代录 |
| `lijing` | 李静 / 综合录入岗 | 全部点位/因子, 可代录 |
| `wangmin` | 王敏 / 福田站点录入岗 | 仅市民中心站(SZ-AQ-001), 全部因子 |
| `chenzq` | 陈志强 / 工业园专项岗 | 仅龙岗工业园站(SZ-AQ-005), 气态污染物(SO₂/NO₂/CO/O₃) |
| `zhaoyu` | 赵宇 / 颗粒物专项岗 | 全部点位, 仅 PM2.5/PM10 |
| `sunqian` | 孙倩 / 福田站点录入岗(停用) | 演示“停用即不可登录/录入” |

生产环境可通过 `flask --app wsgi ensure-admin` 建管理员、`flask --app wsgi set-password <账号> <新密码>` 重置密码。

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
| POST | `/api/auth/login` | 账号密码登录, 返回签名令牌与当前用户(含生效范围) |
| GET | `/api/auth/me` | 当前登录人与其当前生效的可录入范围 |
| GET/POST | `/api/admin/users` | 账号分页/新增(管理员) |
| PUT | `/api/admin/users/{id}` | 账号改名/重置密码/调岗/停用(即时生效) |
| GET/POST | `/api/admin/positions` | 岗位查询/新增(管理员) |
| PUT | `/api/admin/positions/{id}` | 岗位维护(停用/代录权) |
| POST | `/api/admin/positions/{id}/scope-versions` | **新增带生效时间的录入范围版本** |
| GET | `/api/meta/health` | 健康检查(数据库连通性、时区、限值标准) |
| GET | `/api/meta/pollutants` | 监测因子清单与限值 |
| GET | `/api/meta/options` | 枚举选项(监测点、区域、状态、类型等) |
| GET | `/api/meta/overview` | 首页概览聚合数据 |
| GET/POST | `/api/stations` | 台账分页查询 / 新增 |
| GET/PUT/DELETE | `/api/stations/{id}` | 台账详情(含分因子统计) / 更新 / 删除(级联) |
| GET | `/api/stations/options` | 下拉选项(监测点、区域) |
| GET | `/api/stations/summary` | 台账规模统计 |
| GET | `/api/measurements/entry-context` | 录入页上下文(按岗位范围收窄后的点位/因子、代录对象) |
| GET | `/api/measurements` | 监测数据分页查询(含筛选汇总) |
| POST | `/api/measurements/entries` | **成组录入**(需登录, 服务端岗位范围强校验) |
| POST | `/api/measurements/preview` | 超标校验预览(不写库, 同样按范围预检) |
| DELETE | `/api/measurements/{id}` | 删除监测数据(需登录) |
| GET | `/api/measurements/export` | 按条件导出 CSV(含录入人/实际操作人/代录/提交时间) |
| GET | `/api/exceedances` | 超标记录查询(含筛选统计) |
| GET | `/api/exceedances/{id}` | 超标记录详情(含关联监测数据) |
| PATCH | `/api/exceedances/{id}` | 单条标注 |
| POST | `/api/exceedances/annotations` | 批量标注 |
| GET | `/api/exceedances/summary` | 超标统计(状态/等级/高发因子/站点排名) |
| GET | `/api/query/measurements` | 高级条件检索 |
| GET | `/api/query/statistics` | 聚合统计(`group_by` + `metric`) |
| GET | `/api/query/export` | 查询结果导出 CSV |

登录后所有写接口需在请求头携带 `Authorization: Bearer <token>`。未登录返回 `401 UNAUTHORIZED`;
越权(点位/因子超范围、无代录权、非管理员管理)返回 `403 FORBIDDEN`, 错误体含可读 `message` 与逐字段 `fields`。

`POST /api/measurements/entries` 请求示例(录入人/提交时间/数据来源**无需也不会被采信**,
由服务端按登录账号带出; `on_behalf_of_id` 仅在拥有代录权时使用):

```json
{
  "station_id": 1,
  "measured_at": "2026-09-14 10:00",
  "period": "hourly",
  "on_behalf_of_id": null,
  "remark": "在线设备人工比对",
  "overwrite": false,
  "entries": [
    { "pollutant": "PM25", "value": 82.5 },
    { "pollutant": "SO2", "value": 640 },
    { "pollutant": "CO", "value": 1.4 }
  ]
}
```

响应会返回本次新增/更新条数、超标记录、重复项、逐因子判定结果, 以及服务端落库的**录入痕迹**:

```json
{
  "created": [ "..." ],
  "updated": [],
  "exceedances": [ { "pollutant": "SO2", "level": "moderate", "exceed_ratio": 1.28 } ],
  "duplicates": [],
  "submission": {
    "recorder": "王敏", "recorder_id": 3, "operator": "李静", "operator_id": 2,
    "is_proxy": true, "submitted_at": "2026-09-14T10:00:05",
    "data_source": "manual", "scope_version_id": 7
  },
  "summary": { "created_count": 3, "updated_count": 0, "exceeded_count": 1, "duplicate_count": 0 }
}
```

越权示例(岗位只能录颗粒物, 却提交 SO₂, 或选了范围外监测点): HTTP `403`

```json
{
  "error": {
    "code": "OUT_OF_SCOPE",
    "message": "越权提交已被拦截: 因子 SO₂(SO2) 不在可录入范围内。您当前岗位「颗粒物专项岗」的可录入范围为【全部监测点】与【仅 PM2.5、PM10】; 范围如需调整请联系管理员, 调整自设定的生效时间起仅影响此后的录入。",
    "fields": { "SO2": "out_of_scope" }
  }
}
```

## 岗位与录入范围

- **岗位(Position)**: 决定可录入范围; 管理员岗位(`is_admin`)不做点位/因子限制, 且可管理岗位与人员。
- **范围版本(PositionScopeVersion)**: 岗位下按 `effective_from` 挂接多个版本, 录入时取“当前时刻已生效的最新一版”。
  支持未来生效(到期自动切换)与立即生效; 版本内用“全部 / 显式编码清单”分别控制点位与因子。
- **用户(User)**: 归属于一个岗位; 停用账号或停用岗位即不能登录/录入, 调岗后范围即时变为新岗位口径。
- **校验位置**: `services/auth_service.assert_can_record` 在写库前统一拦截, API 层无法绕过;
  录入页的点位下拉、因子表单仅做体验层收窄(`entry-context`), 不是安全边界。
- **代录**: 岗位需 `can_proxy`; 代录时按**操作人**的范围校验, 数据 `recorder` 归属被代录人、`operator` 记实际操作人并置 `is_proxy=true`。

## 数据模型

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `positions` | `code`(唯一) `name` `is_admin` `can_proxy` `active` | 岗位 |
| `position_scope_versions` | `position_id` `effective_from` `all_stations` `station_codes_text` `all_pollutants` `pollutant_codes_text` | 带生效时间的录入范围版本(编码快照) |
| `users` | `username`(唯一) `display_name` `password_hash` `position_id` `active` `last_login_at` | 登录账号 |
| `stations` | `code`(唯一) `name` `area` `station_type` `status` `longitude/latitude` `installed_at` | 监测点台账 |
| `measurements` | `station_id` `pollutant` `period` `value` `limit_value` `exceed_ratio` `is_exceeded` `measured_at` `data_source` `recorder_id/recorder` `operator_id/operator_name` `is_proxy` `submitted_at` `scope_version_id` `scope_position_id` | 监测数据; `(station_id, pollutant, period, measured_at)` 唯一 |
| `exceedances` | `measurement_id`(唯一) `status` `level` `note` `annotator` `annotated_at` | 超标记录与人工标注 |

`measurements` 中的 `recorder_*` 是数据归属录入人(代录时为被代录人), `operator_*` 是实际提交人;
`scope_version_id / scope_position_id` 是**登记当时口径快照**, 范围调整后历史数据归属保持不变。
删除监测点会级联清理其监测数据与超标记录; 删除监测数据会同时删除对应超标记录。

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
python -m pytest -q          # 64 个用例: 台账 CRUD/级联、录入与超标判定、岗位授权/代录/范围生效、标注规则、查询统计与导出、元数据接口

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
