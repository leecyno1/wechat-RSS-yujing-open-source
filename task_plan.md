# RSS Multi-Source Integration Task Plan

## Goal
在现有微信公众号订阅系统中，新增可扩展的“多源订阅”底座：先支持标准 RSS/Atom URL，再支持 RSSHub 路由接入，保持现有微信链路不回归。

## Phases
- [x] Phase 0: 保存仓库检查点
- [x] Phase 1: 领域模型扩展（Feed 支持 source_type/source_url/source_key/source_config）
- [x] Phase 2: 适配器层实现（RSS/Atom 解析 + RSSHub URL 构造）
- [x] Phase 3: API 接入（新增 source 管理与刷新接口）
- [x] Phase 4: 测试与验证（先红后绿，最小可行测试）
- [x] Phase 5: 文档与运行说明

## Risks
- 现有查询大量依赖 `faker_id != ""`，直接改动容易影响微信公众号链路。
- 数据库结构在现网通过 `data_sync` 同步，需要确保新增列可自动补齐。
- 部分 RSS 内容缺少发布时间/摘要，需兼容兜底。

## Decisions
- 先不改现有 UI，先把后端能力打通并保留微信原行为。
- 以 `source_type=wechat|rss|rsshub` 进行渐进扩展。
- 先引入“手动刷新接口”验证，再接自动调度。

## Done
- 新增 `core/source/adapters.py`：RSS/Atom 解析、RSSHub URL 组装、源 key 规范化、远程抓取。
- 新增 `apis/sources.py`：`/sources/feeds` 新增来源、列表、刷新接口。
- 扩展 `feeds` 模型多源字段；`web.py` 注册 sources 路由。
- 新增测试 `tests/test_source_adapters.py`，验证解析和 URL 规则。
