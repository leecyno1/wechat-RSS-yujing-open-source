# Service REST API（给其它项目调用）

本项目后端为 FastAPI，可通过 Service API 以 **API Key** 的方式提供文章与洞察数据（精华/关键信息/全文拆解）给其它项目调用。

## 启用

在运行环境中设置 `SERVICE_API_KEYS`（逗号分隔），并通过请求头 `X-API-Key` 访问接口。

示例（本地容器 compose/.env.local）：

```bash
SERVICE_API_KEYS=dev-key-1,dev-key-2
```

## Base URL

默认 API_BASE 为 `/api/v1/wx`，因此 Service API 实际路径为：

`/api/v1/wx/service/*`

## 接口

- `GET /api/v1/wx/service/ping`
- `GET /api/v1/wx/service/channels`
- `GET /api/v1/wx/service/channels/{channel_id}/articles`
- `GET /api/v1/wx/service/articles/{article_id}`

## 调用示例

```bash
BASE=http://localhost:8001
KEY=dev-key-1

curl -H "X-API-Key: $KEY" "$BASE/api/v1/wx/service/ping"
curl -H "X-API-Key: $KEY" "$BASE/api/v1/wx/service/channels?limit=50"
curl -H "X-API-Key: $KEY" "$BASE/api/v1/wx/service/channels/all/articles?limit=30"
curl -H "X-API-Key: $KEY" "$BASE/api/v1/wx/service/articles/<ARTICLE_ID>?include_content=true&include_llm=true"
```

## 响应格式

统一为：

```json
{ "code": 0, "message": "success", "data": ... }
```

