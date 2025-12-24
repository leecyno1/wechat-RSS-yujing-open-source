__package__ = "driver"
from core.config import Config,cfg
# 确保data目录和wx.lic文件存在
import os

from core.print import print_success
lic_path="./data/wx.lic"
os.makedirs(os.path.dirname(lic_path), exist_ok=True)
if not os.path.exists(lic_path):
    with open(lic_path, "w") as f:
        f.write("{}")
wx_cfg = Config(lic_path)

def _mask_secret(s: str, keep_start: int = 6, keep_end: int = 4) -> str:
    if not s:
        return ""
    if len(s) <= keep_start + keep_end + 3:
        return s[:2] + "***"
    return f"{s[:keep_start]}***{s[-keep_end:]}"


def _seed_from_env():
    token = os.getenv("WX_TOKEN", "") or os.getenv("WECHAT_MP_TOKEN", "")
    cookie = os.getenv("WX_COOKIE", "") or os.getenv("WECHAT_MP_COOKIE", "")
    fingerprint = os.getenv("WX_FINGERPRINT", "") or os.getenv("WECHAT_MP_FINGERPRINT", "")
    force = str(os.getenv("WX_FORCE_SESSION", "False")).lower() == "true"

    if not token or not cookie:
        return

    existing_token = str(wx_cfg.get("token", "") or "")
    existing_cookie = str(wx_cfg.get("cookie", "") or "")
    if not force and existing_token and existing_cookie:
        return

    set_token(
        {
            "token": token,
            "cookies_str": cookie,
            "fingerprint": fingerprint,
            "expiry": {},
        }
    )


_seed_from_env()

def set_token(data:any,ext_data:any=None):

    """
    设置微信登录的Token和Cookie信息
    :param data: 包含Token和Cookie信息的字典
    """
    if data.get("token", "") == "":
        return
    wx_cfg.set("token", data.get("token", ""))
    wx_cfg.set("cookie", data.get("cookies_str", ""))
    wx_cfg.set("fingerprint", data.get("fingerprint", ""))
    wx_cfg.set("expiry", data.get("expiry", {}))
    exp = ""
    try:
        exp = str(data.get("expiry", {}).get("expiry_time", ""))
    except Exception:
        exp = ""
    print_success(
        f"Token:{_mask_secret(str(data.get('token','')))} CookieLen:{len(str(data.get('cookies_str','')))} "
        f"到期时间:{exp}\n"
    )
    if ext_data is not None:
        wx_cfg.set("ext_data", ext_data)
    wx_cfg.save_config()
    wx_cfg.reload()
    from jobs.notice import sys_notice
    
#     sys_notice(f"""WeRss授权成功
# - Token: {data.get("token")}
# - Expiry: {data.get("expiry")['expiry_time']}
# """, str(cfg.get("server.code_title","WeRss授权成功")))


def get(key:str,default:str="")->str:
    return str(wx_cfg.get(key, default))
