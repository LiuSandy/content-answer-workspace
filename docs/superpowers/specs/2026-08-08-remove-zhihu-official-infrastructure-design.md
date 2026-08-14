# 移除知乎官方基础设施设计

## 目标

删除 `app/infrastructure/zhihu/` 及其全部代码引用。Agent 只注册并调用
`app/application/agent/tools/` 中定义的平台工具；知乎工具仅保留现有网页采集路径，
不再调用知乎官方 API。

## 架构调整

- 删除 `ZhihuOfficialClient` 和 `ZhihuOfficialCollector`。
- `zhihu_search` 删除官方 API 优先分支，直接调用现有网页采集服务并保持当前 JSON
  输出结构，`mode` 固定为 `web`。
- `CollectorFactory` 和 `ZhihuSource` 只使用 `ZhihuCollector`；`auto` 等同于网页模式，
  显式请求 `official` 时返回清晰的“不支持”错误。
- 删除依赖官方客户端的独立 `/api/hotlist` 能力，包括后端路由、服务、Agent 热榜分析图
  及前端隐藏的 `/hotlist` 页面入口。
- 机会扫描不再主动拉取知乎热榜；保留机会列表、评分和人工管理等不依赖热榜拉取的能力，
  定时扫描安全返回零条结果。

## 错误处理与兼容性

- 不再读取或要求 `ZHIHU_ACCESS_SECRET`。
- 网页采集仍沿用当前 `ZHIHU_COOKIE` 和网络错误处理方式。
- 已有普通知乎搜索、URL 导入和网页批量采集继续可用。
- `/api/hotlist` 属于有意删除的接口，调用方不做兼容代理。

## 测试

- 增加应用边界测试：服务可正常导入，且不再注册 `/api/hotlist` 路由。
- 调整知乎工具测试，验证其只走网页采集并输出 `mode=web`。
- 调整采集器工厂和知乎内容源测试，验证 `auto/web` 使用网页采集，`official` 明确失败。
- 删除或更新热榜 API、热榜分析和机会扫描中依赖官方热榜的测试。
- 运行相关后端测试、后端完整测试，并对受影响前端执行 typecheck。

## 范围保护

不修改当前未提交的 `frontend/src/features/chat/` 文件，也不改动普通网页搜索、知乎 URL
解析或其他平台工具。
