# WebGIS 架构第一阶段整理记录

## 本次目标

本次先做低风险、可验证的结构整理，不大规模改写业务逻辑。目标是让后续新增功能时有更清晰的入口、注册表和拆分路线。

## 已落地边界

- 后端 `app.py` 只负责创建 FastAPI、接入中间件、挂载生命周期和注册路由。
- API 路由注册集中到 `backend/api/routes.py`，每个业务模块仍保留自己的 `APIRouter` 所有权。
- 健康检查、客户端 IP、接口目录等系统端点迁移到 `backend/api/system.py`。
- 启动/关闭资源管理集中到 `backend/core/lifecycle.py`，包括认证存储初始化与共享 HTTP 客户端生命周期。
- CORS 参数集中到 `backend/core/cors.py`，当前保持原行为，后续可按环境收紧。
- 前端底图注册表继续作为在线底图唯一来源；鹰眼视图通过独立 map feature 复用该注册表。

## 当前主要架构风险

- `frontend/src/components/TOCPanel.vue`、`HomeView.vue`、`MapContainer.vue` 仍然过大，后续新增工具容易继续堆在组件层。
- `backend/api/agent_chat.py`、`auth.py`、`statistics.py` 聚合了路由、服务逻辑、数据访问与配置处理，测试和复用成本较高。
- 后端数据库初始化仍集中在兼容 sqlite 风格的 PostgreSQL 适配层中，短期要保持兼容，长期建议引入显式 migration。
- CORS 当前允许所有 HTTP/HTTPS 源，适合临时开发，但正式部署应改为环境变量白名单。

## 建议后续阶段

1. 拆 `TOCPanel.vue`：先按“上传入口、图层树、工具动作、样式编辑”拆子组件与 composable。
2. 拆 `MapContainer.vue`：继续把鹰眼、底图卷帘、搜索、路线、罗盘桥接等能力迁入 `composables/map/features/`。
3. 拆后端大模块：为 `agent_chat`、`auth`、`statistics` 建立 `services/` 和 `repositories/`，路由只做参数校验与响应编排。
4. 数据库治理：保留当前兼容适配器，对新增表和字段改用版本化 migration，避免初始化函数继续膨胀。
5. 配置治理：把 CORS、第三方 key、模型供应商、配额规则统一走环境/数据库配置层。
