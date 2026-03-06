# Findings

## 2026-03-06
- 当前项目许可证为 MIT。
- 上游目标：RSSHub/FreshRSS 为 AGPL-3.0，RSS-Bridge 为 Unlicense，代码级合并风险高于协议级接入。
- 当前数据模型核心：`feeds` + `articles` + `user_subscriptions`，具备多源扩展潜力。
- `init_sys.sync_models()` 会调用 `data_sync.DatabaseSynchronizer`，支持给已有表自动 `ALTER TABLE ADD COLUMN`。
- 队列层已支持多 worker，适合后续按 source_type 限流与并发控制。
