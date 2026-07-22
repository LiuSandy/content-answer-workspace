# 需求规格说明书：PostgreSQL 默认无感数据保护与自动化平滑迁移

> **文档状态**：草案 (Draft) - 等待用户评审确认  
> **功能标识**：`feature-auto-data-preservation`  
> **规范遵循**：Superpowers Specification Standard  

---

## 1. 概述与背景 (Overview & Context)

在本地内容工作台中，系统依赖 PostgreSQL 存储采集的问题与回答数据（如 `questions`, `answers` 表），同时通过扩展（如 `vector`, `pg_search`）提供私有资料库 RAG 向量检索能力。

### 1.1 问题痛点
在传统的升级流程中，当替换数据库 Docker 镜像、调整挂载目录或进行架构演进时，常常导致历史数据卷被遗弃或破坏，需要用户手工敲命令导出导入恢复数据。这种做法违反了工程化质量标准。

### 1.2 核心目标
建立一套**工程化、自动化、默认无损的数据持久化与自动迁移机制**：
无论是镜像升级、版本变更、数据卷目录演进还是 Alembic 迁移，系统必须做到：
* **数据零丢失 (Zero Data Loss)**：历史采集数据默认 100% 留存。
* **0 人工干预 (Unattended Automation)**：无需用户执行任何 `pg_dump` 或恢复命令，系统自动在后台完成无感缝合。
* **纯增量兼容 (Non-Destructive Evolution)**：对现有数据库 Schema 只做增量叠加，禁止破坏性删除。

---

## 2. 核心架构与设计规范 (Architectural Specifications)

### 2.1 物理数据卷收敛规范 (Volume Standard)
* **唯一主持久化卷**：统一收敛使用 `postgres_data` 作为唯一的数据库物理数据卷。
* **挂载目录规范**：在 `docker-compose.yml` 中统一通过环境变量 `PGDATA: /var/lib/postgresql/data/pgdata` 进行挂载。既符合新版 Docker 入口脚本要求，又保证旧数据与增量扩展数据存放在同一物理卷中。

### 2.2 自动化无感数据平滑缝合规范 (Auto-Migration Standard)
当启动服务或容器时，系统将触发自动迁移挂钩脚本（`Auto-Migration Hook`），执行以下标准流程：

```text
[启动服务 / 容器]
       │
       ▼
[检测数据卷中是否存在旧格式数据？]
       ├── 是 ──► [自动解包旧数据快照 ➔ 自动缝合至 ParadeDB 新表结构 ➔ 标记 .migrated]
       └── 否 ──► [直接秒级挂载启动]
       │
       ▼
[自动应用 Alembic 增量 Migration (IF NOT EXISTS)]
       │
       ▼
[后端就绪，页面 100% 完整展示历史采集数据与新功能]
```

### 2.3 增量非破坏性 Migration 规范
所有 Alembic 迁移脚本必须满足：
1. 全量使用 `IF NOT EXISTS` 检查表与扩展。
2. 绝对禁止包含 `DROP TABLE` 或 `DROP COLUMN` 指令。
3. 向量扩展 `vector` 和 BM25 扩展 `pg_search` 作为外挂增量列及外挂索引叠加在已有 `questions` / `answers` 表之上。

### 2.4 本地快照容灾自愈规范 (Backup & Recovery Guard)
* 在后端启动（`lifespan` 阶段），`db_guard` 自动在项目 `output/backups/` 目录下建立带有时间戳的数据库物理/逻辑快照。
* 即使遇到物理磁盘故障，系统支持根据快照自动自愈恢复。

---

## 3. 详细交互与契约规范 (Interface Specifications)

### 3.1 用户体验契约 (User Experience Contract)
* **用户输入**：用户只需按照常规方式执行 `docker compose up -d` 和启动后端/前端。
* **用户输出**：打开网页 `http://127.0.0.1:5173`，工作台页面**默认、无感、直接完整展现之前采集的所有问题与回答数据**，同时私有资料库 RAG 功能正常可用。
* **异常处理**：若数据库在迁移中出现异常，系统自动提示并退回到本地最新备份，绝不静默丢数据。

---

## 4. 验收标准 (Acceptance Criteria)

- [ ] **AC-1 (卷归一化)**：`docker-compose.yml` 中仅保留统一的 `postgres_data` 持久化卷，并配置 `PGDATA: /var/lib/postgresql/data/pgdata`。
- [ ] **AC-2 (旧数据无感带入)**：模拟包含旧版采集数据的数据库镜像升级，运行服务后，新 ParadeDB 数据库中全量自动包含旧版 `questions` 与 `answers` 记录，用户无需敲击任何导出导入命令。
- [ ] **AC-3 (非破坏性 Migration)**：多次运行 `uv run alembic upgrade head`，现有数据行数与字段完全不受破坏。
- [ ] **AC-4 (启动自动快照)**：后端服务启动后，`output/backups/` 目录下自动生成有效的数据库备份文件。

---

## 5. 待确认事项 (Open Questions for Approval)

1. 请确认自动备份文件存储路径设为 `output/backups/` 是否合适？
2. 请确认是否同意上述验收标准 AC-1 ~ AC-4 作为功能落地的准则？
