# [实现计划] PostgreSQL 默认无感数据保护与自动化平滑迁移

> **文档状态**：已制定 (Drafting) - 等待用户评审确认  
> **关联 Spec**：[docs/specs/feature-auto-data-preservation.md](file:///Users/lius/Desktop/self/content-answer-workspace/docs/specs/feature-auto-data-preservation.md)  

---

## 1. 拟修改与新增的文件列表

### 1.1 容器配置层 (Docker Infrastructure)
* **[MODIFY] [docker-compose.yml](file:///Users/lius/Desktop/self/content-answer-workspace/docker-compose.yml)**
  * **改动内容**：彻底清理多余临时数据卷定义，统一收敛回原有的主持久化数据卷 `postgres_data`。
  * **挂载配置**：确认 `environment` 中挂载子目录 `PGDATA: /var/lib/postgresql/data/pgdata`。

### 1.2 自动化无感迁移服务 (Auto Migration Engine)
* **[NEW] [scripts/auto_migrate_db.py](file:///Users/lius/Desktop/self/content-answer-workspace/scripts/auto_migrate_db.py)**
  * **功能**：自动检测 `postgres_data` 卷中是否存在旧版 `questions` / `answers` 采集记录。
  * **无感缝合**：若检测到旧记录且新 ParadeDB 表尚未合并，自动在后台读取旧记录 ➔ 新表初始化 ➔ 全量缝合导入 ➔ 生成 `.migration_completed` 标记。全程 **0 人工命令**。
* **[NEW] [app/core/db_guard.py](file:///Users/lius/Desktop/self/content-answer-workspace/app/core/db_guard.py)**
  * **功能**：后端启动时自动建立带时间戳的物理/逻辑增量快照（存放在 `output/backups/`）。
  * **就绪检测**：自动检测数据库服务与扩展连通状态。

### 1.3 应用服务端集成 (Application Integration)
* **[MODIFY] [app/server.py](file:///Users/lius/Desktop/self/content-answer-workspace/app/server.py)**
  * **改动内容**：在 `lifespan` 启动阶段注入 `db_guard` 快照挂载与启动检测逻辑。

### 1.4 自动化测试套件 (Verification Suite)
* **[NEW] [tests/test_auto_data_preservation.py](file:///Users/lius/Desktop/self/content-answer-workspace/tests/test_auto_data_preservation.py)**
  * **测试内容**：模拟旧数据库环境注入与升级全过程，校验数据 100% 自动无感平滑迁移，且旧数据条数与内容零丢失。

---

## 2. 详细执行步骤与 TDD 流程

1. **Step 1 (TDD 测试先行)**：创建 `tests/test_auto_data_preservation.py`，编写模拟旧数据无感迁移与自愈快照的失败测试。
2. **Step 2 (编写无感迁移脚本)**：实现 `scripts/auto_migrate_db.py` 与 `app/core/db_guard.py`，确保旧数据自动识别与缝合。
3. **Step 3 (集成应用与容器配置)**：更新 `docker-compose.yml` 统一数据卷，并在 `app/server.py` lifespan 挂载自动快照逻辑。
4. **Step 4 (实证校验与提交)**：运行全套 pytest 测试与类型检查，确认 100% 通过后提交代码。

---

## 3. 验证计划

### 自动化测试命令
```bash
uv run pytest tests/test_auto_data_preservation.py -v
```

### 实际链路校验
1. 校验 `docker compose up -d postgres` 后，`scripts/auto_migrate_db.py` 能自动触发并成功缝合数据。
2. 校验后端启动后 `output/backups/` 目录下生成时间戳快照文件。
3. 校验 `uv run alembic upgrade head` 在已有数据上运行无任何报错或数据损坏。
