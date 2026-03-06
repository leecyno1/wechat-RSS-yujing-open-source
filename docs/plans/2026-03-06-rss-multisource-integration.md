# RSS Multi-Source Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为项目新增可扩展多源订阅能力，先接 RSS/Atom 与 RSSHub，保持微信公众号功能稳定。

**Architecture:** 在 Feed 模型增加来源元数据，通过 Source Adapter 归一化不同来源为统一 Article 入库结构；新增 source API 完成新增来源与刷新。微信公众号路径保持不变，逐步迁移通用查询。

**Tech Stack:** FastAPI, SQLAlchemy, requests/xml.etree, existing TaskQueue/InsightsQueue.

---

### Task 1: 模型扩展
- 修改 `core/models/feed.py` 增加来源字段。
- 编写测试验证模型字段存在并可写。

### Task 2: 适配器实现
- 新建 `core/source/adapters.py`，实现 RSS/Atom 解析与 RSSHub URL 生成。
- 先写失败测试，再实现最小逻辑。

### Task 3: API 接入
- 新建 `apis/sources.py`：新增 source feed、手动刷新 source feed。
- 通过统一入库函数写入 `articles`。

### Task 4: 路由注册与兼容
- 在 `web.py` 注册新 router。
- 不破坏现有 `mps` 与 `channels` 行为。

### Task 5: 校验
- 运行新增测试与关键模块语法校验。
- 更新文档说明最小使用流程。
