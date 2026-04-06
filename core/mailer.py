from __future__ import annotations

import smtplib
from email.message import EmailMessage

from core.config import cfg


def _as_bool(v: object, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if not s:
        return default
    return s in {"1", "true", "yes", "on"}


def mail_enabled() -> bool:
    # Backward compatible: support both `mail.enable` and `mail.enabled`.
    v = cfg.get("mail.enable", None)
    if v is None:
        v = cfg.get("mail.enabled", False)
    return _as_bool(v, False)


def send_mail(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    host = str(cfg.get("mail.smtp.host", "") or "").strip()
    port = int(cfg.get("mail.smtp.port", 587) or 587)
    username = str(cfg.get("mail.smtp.username", "") or "").strip()
    password = str(cfg.get("mail.smtp.password", "") or "").strip()
    from_email = str(cfg.get("mail.from_email", "") or "").strip()
    from_name = str(cfg.get("mail.from_name", "大圣之怒订阅助手") or "大圣之怒订阅助手").strip()
    use_tls = _as_bool(cfg.get("mail.smtp.use_tls", True), True)
    use_ssl = _as_bool(cfg.get("mail.smtp.use_ssl", False), False)
    timeout = float(cfg.get("mail.smtp.timeout", 15) or 15)

    if not mail_enabled():
        raise RuntimeError("邮件服务未启用（mail.enabled=false）")
    if not host:
        raise RuntimeError("邮件服务未配置 smtp.host")
    if not from_email:
        raise RuntimeError("邮件服务未配置 from_email")
    if not to_email:
        raise RuntimeError("收件邮箱不能为空")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg.set_content(text_body or "")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=timeout) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(msg)
