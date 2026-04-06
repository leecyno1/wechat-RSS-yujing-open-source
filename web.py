from fastapi import FastAPI, Request, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from fastapi.openapi.models import OAuthFlowPassword
from fastapi.openapi.utils import get_openapi
from apis.auth import router as auth_router
from apis.user import router as user_router
from apis.article import router as article_router
from apis.mps import router as wx_router
from apis.res import router as res_router
from apis.rss import router as rss_router,feed_router
from apis.config_management import router as config_router
from apis.message_task import router as task_router
from apis.sys_info import router as sys_info_router
from apis.tags import router as tags_router
from apis.export import router as export_router
from apis.tools import router as tools_router
from apis.github_update import router as github_router
from apis.insights import router as insights_router
from apis.favorites import router as favorites_router
from apis.notes import router as notes_router
from apis.library import router as library_router
from apis.public import router as public_router
from apis.channels import router as channels_router
from apis.service_api import router as service_router
from apis.sources import router as sources_router
from apis.parser import router as parser_router
import apis
import os
import re
from core.config import cfg,VERSION,API_BASE
from apis.base import error_response


def _split_csv(raw: str, *, fallback: list[str]) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return fallback
    out = [x.strip() for x in text.split(",") if x.strip()]
    return out or fallback

app = FastAPI(
    title="WeRSS API",
    description="微信公众号RSS生成服务API文档",
    version="1.0.0",
    docs_url="/api/docs",  # 指定文档路径
    redoc_url="/api/redoc",  # 指定Redoc路径
    # 指定OpenAPI schema路径
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {
            "name": "认证",
            "description": "用户认证相关接口",
        }
    ],
    swagger_ui_parameters={
        "persistAuthorization": True,
        "withCredentials": True,
    }
)

# CORS配置（默认仅放行本地开发域名；生产建议通过 CORS_ALLOW_ORIGINS 精确配置）
_cors_allow_origins = _split_csv(
    str(cfg.get("cors.allow_origins", "") or ""),
    fallback=["http://localhost:5173", "http://127.0.0.1:5173"],
)


def _normalize_error_payload(detail, status_code: int):
    if isinstance(detail, dict):
        code = detail.get("code", status_code)
        message = detail.get("message")
        data = detail.get("data")
        if not message:
            message = str(detail.get("detail") or f"HTTP {status_code} Error")
        return error_response(code=int(code), message=str(message), data=data)
    if isinstance(detail, str) and detail.strip():
        return error_response(code=int(status_code), message=detail.strip())
    return error_response(code=int(status_code), message=f"HTTP {status_code} Error")


def _translate_validation_message(msg: str) -> str:
    text = str(msg or "").strip()
    if not text:
        return "请求参数校验失败"
    m = re.search(r"Input should be less than or equal to (\d+)", text, re.IGNORECASE)
    if m:
        return f"输入值不能大于 {m.group(1)}"
    m = re.search(r"Input should be greater than or equal to (\d+)", text, re.IGNORECASE)
    if m:
        return f"输入值不能小于 {m.group(1)}"
    m = re.search(r"String should have at most (\d+) characters?", text, re.IGNORECASE)
    if m:
        return f"文本长度不能超过 {m.group(1)} 个字符"
    m = re.search(r"String should have at least (\d+) characters?", text, re.IGNORECASE)
    if m:
        return f"文本长度不能少于 {m.group(1)} 个字符"
    if "Field required" in text:
        return "缺少必填字段"
    if "valid integer" in text:
        return "请输入有效整数"
    if "valid number" in text:
        return "请输入有效数字"
    if "valid boolean" in text:
        return "请输入有效布尔值"
    if "valid string" in text:
        return "请输入有效文本"
    if "valid list" in text:
        return "请输入有效列表"
    if "valid dictionary" in text or "valid object" in text:
        return "请输入有效对象"
    return text


def _format_validation_field(loc: tuple | list | None) -> str:
    if not isinstance(loc, (tuple, list)):
        return ""
    parts = [str(x) for x in loc if str(x) not in ("body", "query", "path", "header")]
    if not parts:
        return ""
    return ".".join(parts)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    payload = _normalize_error_payload(exc.detail, int(exc.status_code))
    return JSONResponse(status_code=int(exc.status_code), content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    errs = exc.errors() or []
    first = errs[0] if errs else {}
    first_msg = _translate_validation_message(str(first.get("msg") or "Request validation failed"))
    first_field = _format_validation_field(first.get("loc"))
    msg = f"{first_field}: {first_msg}" if first_field else first_msg
    normalized_errors = []
    for item in errs:
        field = _format_validation_field(item.get("loc"))
        nmsg = _translate_validation_message(str(item.get("msg") or "Request validation failed"))
        normalized_errors.append(
            {
                "field": field,
                "message": nmsg,
                "type": str(item.get("type") or ""),
            }
        )
    payload = error_response(code=42201, message=msg, data={"errors": normalized_errors})
    return JSONResponse(status_code=422, content=payload)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    if bool(cfg.get("debug", False)):
        payload = error_response(code=50000, message=f"Internal Server Error: {str(exc)}")
    else:
        payload = error_response(code=50000, message="Internal Server Error")
    return JSONResponse(status_code=500, content=payload)
_cors_allow_methods = _split_csv(
    str(cfg.get("cors.allow_methods", "") or ""),
    fallback=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
_cors_allow_headers = _split_csv(
    str(cfg.get("cors.allow_headers", "") or ""),
    fallback=["Authorization", "Content-Type", "X-API-Key"],
)
_cors_allow_origin_regex = str(cfg.get("cors.allow_origin_regex", "") or "").strip() or None
_cors_allow_credentials = bool(cfg.get("cors.allow_credentials", True))
# 防止 '*' + credentials 组合造成浏览器安全风险
if "*" in _cors_allow_origins and _cors_allow_credentials:
    _cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_origin_regex=_cors_allow_origin_regex,
    allow_credentials=_cors_allow_credentials,
    allow_methods=_cors_allow_methods,
    allow_headers=_cors_allow_headers,
)
@app.middleware("http")
async def add_custom_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Version"] = VERSION
    response.headers["X-Powered-By"] = "Rachel"
    response.headers["GITHUB"] = "https://github.com/rachelos/we-mp-rss"
    response.headers["Server"] = cfg.get("app_name", "WeRSS")
    return response
# 创建API路由分组
api_router = APIRouter(prefix=f"{API_BASE}")
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(article_router)
api_router.include_router(wx_router)
api_router.include_router(config_router)
api_router.include_router(task_router)
api_router.include_router(sys_info_router)
api_router.include_router(tags_router)
api_router.include_router(export_router)
api_router.include_router(tools_router)
api_router.include_router(github_router)
api_router.include_router(insights_router)
api_router.include_router(favorites_router)
api_router.include_router(notes_router)
api_router.include_router(library_router)
api_router.include_router(public_router)
api_router.include_router(channels_router)
api_router.include_router(service_router)
api_router.include_router(sources_router)
api_router.include_router(parser_router)

# 公众号绑定/推送链路默认关闭（当前版本仅保留站内订阅能力）。
if bool(cfg.get("feature.wechat_binding_push_enable", False)):
    from apis.digest import router as digest_router
    from apis.binding import router as binding_router
    from apis.wechat_official import legacy_router as wechat_official_legacy_router
    from apis.wechat_official import router as wechat_official_router
    from apis.langbot_webhook import router as langbot_router

    api_router.include_router(digest_router)
    api_router.include_router(binding_router)
    api_router.include_router(wechat_official_router)
    api_router.include_router(langbot_router)
    app.include_router(wechat_official_legacy_router)

resource_router = APIRouter(prefix="/static")
resource_router.include_router(res_router)
feeds_router = APIRouter()
feeds_router.include_router(rss_router)
feeds_router.include_router(feed_router)
# 注册API路由分组
app.include_router(api_router)
app.include_router(resource_router)
app.include_router(feeds_router)

# 静态文件服务配置
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="static"), name="static")
from core.res.avatar import files_dir
app.mount("/files", StaticFiles(directory=files_dir), name="files")
# app.mount("/docs", StaticFiles(directory="./data/docs"), name="docs")

# Some ingress / load balancers use HEAD probes. FastAPI routes do not always auto-add HEAD,
# so we provide explicit lightweight endpoints to avoid 405 health-check failures.
@app.get("/healthz", tags=["默认"], include_in_schema=False)
async def healthz_get():
    return {"ok": True, "version": VERSION}


@app.head("/healthz", tags=["默认"], include_in_schema=False)
async def healthz_head():
    return Response(status_code=200)


@app.head("/", tags=["默认"], include_in_schema=False)
async def head_root():
    return Response(status_code=200)

@app.get("/{path:path}",tags=['默认'],include_in_schema=False)
async def serve_vue_app(request: Request, path: str):
    """处理Vue应用路由"""
    # 排除API和静态文件路由
    if path.startswith(('api', 'assets', 'static')) or path in ['favicon.ico','vite.svg','logo.svg']:
        return JSONResponse(status_code=404, content=error_response(code=404, message="Not Found"))
    
    # 返回Vue入口文件
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    return JSONResponse(status_code=404, content=error_response(code=404, message="Not Found"))

@app.get("/",tags=['默认'],include_in_schema=False)
async def serve_root(request: Request):
    """处理根路由"""
    return await serve_vue_app(request, "")
