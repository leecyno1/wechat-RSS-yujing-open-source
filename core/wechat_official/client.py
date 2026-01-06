from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from urllib.parse import quote

from core.config import cfg


def _now_ts() -> int:
    return int(time.time())


def _as_bool(v: Any, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _cache_file() -> str:
    base = str(cfg.get("cache.dir", "./data/cache") or "./data/cache")
    path = os.path.join(base, "wechat_official", "access_token.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: int


_MEM_TOKEN: AccessToken | None = None


class WeChatOfficialClient:
    def __init__(self):
        self.base_url = "https://api.weixin.qq.com"

    def _appid(self) -> str:
        return str(cfg.get("wechat_official.appid", "") or "").strip()

    def _secret(self) -> str:
        return str(cfg.get("wechat_official.appsecret", "") or "").strip()

    def _timeout(self) -> int:
        try:
            return int(cfg.get("wechat_official.http_timeout", 10) or 10)
        except Exception:
            return 10

    def _use_stable_token(self) -> bool:
        return _as_bool(cfg.get("wechat_official.use_stable_token", True), True)

    def _load_cached(self) -> AccessToken | None:
        try:
            raw = open(_cache_file(), "r", encoding="utf-8").read()
            obj = json.loads(raw)
            token = str(obj.get("access_token") or "")
            expires_at = int(obj.get("expires_at") or 0)
            appid = str(obj.get("appid") or "")
            if not token or expires_at <= _now_ts() or (appid and appid != self._appid()):
                return None
            return AccessToken(token=token, expires_at=expires_at)
        except Exception:
            return None

    def _save_cached(self, token: AccessToken) -> None:
        try:
            path = _cache_file()
            tmp = path + ".tmp"
            payload = {"appid": self._appid(), "access_token": token.token, "expires_at": int(token.expires_at)}
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False))
            os.replace(tmp, path)
        except Exception:
            return None

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        global _MEM_TOKEN

        if not force_refresh and _MEM_TOKEN and _MEM_TOKEN.expires_at > _now_ts():
            return _MEM_TOKEN.token

        if not force_refresh:
            cached = self._load_cached()
            if cached and cached.expires_at > _now_ts():
                _MEM_TOKEN = cached
                return cached.token

        appid = self._appid()
        secret = self._secret()
        if not appid or not secret:
            raise RuntimeError("WeChatOfficialClient: missing wechat_official.appid/appsecret")

        if self._use_stable_token():
            url = f"{self.base_url}/cgi-bin/stable_token"
            resp = requests.post(
                url,
                json={"grant_type": "client_credential", "appid": appid, "secret": secret, "force_refresh": bool(force_refresh)},
                timeout=self._timeout(),
            )
            data = resp.json()
        else:
            url = f"{self.base_url}/cgi-bin/token"
            resp = requests.get(
                url,
                params={"grant_type": "client_credential", "appid": appid, "secret": secret},
                timeout=self._timeout(),
            )
            data = resp.json()

        if int(data.get("errcode") or 0) != 0:
            raise RuntimeError(f"WeChatOfficialClient: token error {data.get('errcode')}: {data.get('errmsg')}")

        token = str(data.get("access_token") or "").strip()
        expires_in = int(data.get("expires_in") or 0)
        if not token or expires_in <= 0:
            raise RuntimeError("WeChatOfficialClient: invalid token response")

        # Refresh early by 5 minutes.
        expires_at = _now_ts() + max(60, expires_in - 300)
        at = AccessToken(token=token, expires_at=expires_at)
        _MEM_TOKEN = at
        self._save_cached(at)
        return token

    def create_menu(self, menu: dict[str, Any]) -> dict[str, Any]:
        access_token = self.get_access_token()
        url = f"{self.base_url}/cgi-bin/menu/create"
        resp = requests.post(url, params={"access_token": access_token}, json=menu, timeout=self._timeout())
        data = resp.json()
        if int(data.get("errcode") or 0) != 0:
            raise RuntimeError(f"WeChatOfficialClient: menu/create error {data.get('errcode')}: {data.get('errmsg')}")
        return data

    def create_qrcode_ticket(self, *, scene_str: str, expire_seconds: int = 600) -> dict[str, Any]:
        """Create a temporary parameterized QRCode ticket (QR_STR_SCENE).

        `scene_str` should be <= 64 chars; `expire_seconds` max 30 days.
        """
        scene = str(scene_str or "").strip()
        if not scene:
            raise RuntimeError("WeChatOfficialClient: scene_str is required")
        if len(scene) > 64:
            raise RuntimeError("WeChatOfficialClient: scene_str too long (max 64)")
        try:
            exp = int(expire_seconds or 0)
        except Exception:
            exp = 600
        exp = max(60, min(30 * 24 * 3600, exp))

        access_token = self.get_access_token()
        url = f"{self.base_url}/cgi-bin/qrcode/create"
        payload = {"expire_seconds": exp, "action_name": "QR_STR_SCENE", "action_info": {"scene": {"scene_str": scene}}}
        resp = requests.post(url, params={"access_token": access_token}, json=payload, timeout=self._timeout())
        data = resp.json()
        if int(data.get("errcode") or 0) != 0:
            raise RuntimeError(f"WeChatOfficialClient: qrcode/create error {data.get('errcode')}: {data.get('errmsg')}")
        return data

    def show_qrcode_url(self, ticket: str) -> str:
        t = str(ticket or "").strip()
        if not t:
            return ""
        return f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={quote(t, safe='')}"

    def send_custom_text(self, openid: str, content: str) -> dict[str, Any]:
        openid_s = str(openid or "").strip()
        if not openid_s:
            raise RuntimeError("WeChatOfficialClient: openid is required")
        text = str(content or "").strip()
        if not text:
            raise RuntimeError("WeChatOfficialClient: content is required")

        access_token = self.get_access_token()
        url = f"{self.base_url}/cgi-bin/message/custom/send"
        payload = {"touser": openid_s, "msgtype": "text", "text": {"content": text}}
        resp = requests.post(url, params={"access_token": access_token}, json=payload, timeout=self._timeout())
        data = resp.json()
        if int(data.get("errcode") or 0) != 0:
            raise RuntimeError(f"WeChatOfficialClient: custom/send error {data.get('errcode')}: {data.get('errmsg')}")
        return data
