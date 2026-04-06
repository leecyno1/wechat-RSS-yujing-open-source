from core.models.user import User
from core.models.article import Article
from core.models.config_management import ConfigManagement
from core.models.feed import Feed
from core.models.message_task import MessageTask
from core.db import Db,DB
from core.config import cfg
from core.auth import pwd_context
import time
import os
from core.print import print_info, print_error
from datetime import datetime
def init_user(_db: Db):
    username = os.getenv("USERNAME", "admin")
    password = os.getenv("PASSWORD", "admin@123")
    permissions = '["admin","wechat:manage","tag:view","tag:edit","config:view","message_task:view","message_task:edit"]'
    session = None
    try:
        session = _db.get_session()
        now = datetime.now()

        # Upsert admin user (id=0). Older databases may have a plaintext/invalid hash and would never allow login.
        existing = session.query(User).filter(User.id == "0").first()
        if not existing and username:
            existing = session.query(User).filter(User.username == username).first()

        if existing:
            changed = False
            if username and existing.username != username:
                existing.username = username
                changed = True
            if existing.role != "admin":
                existing.role = "admin"
                changed = True
            if str(existing.permissions or "") != permissions:
                existing.permissions = permissions
                changed = True
            if not bool(getattr(existing, "is_active", True)):
                existing.is_active = True
                changed = True

            # Repair password hash if it doesn't verify with env PASSWORD.
            try:
                ok = bool(password) and pwd_context.verify(password, str(existing.password_hash or ""))
            except Exception:
                ok = False
            if not ok:
                existing.password_hash = pwd_context.hash(password)
                changed = True

            if changed:
                existing.updated_at = now
                session.add(existing)
                session.commit()
            print_info(f"初始化用户成功,请使用以下凭据登录：{existing.username}")
            return

        session.add(
            User(
                id="0",
                username=username,
                password_hash=pwd_context.hash(password),
                role="admin",
                permissions=permissions,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        print_info(f"初始化用户成功,请使用以下凭据登录：{username}")
    except Exception:
        try:
            if session is not None:
                session.rollback()
        except Exception:
            pass
    finally:
        try:
            if session is not None:
                session.close()
        except Exception:
            pass
def sync_models():
     # 同步模型到表结构
         from data_sync import DatabaseSynchronizer
         DB.create_tables()
         time.sleep(3)
         synchronizer = DatabaseSynchronizer(db_url=cfg.get("db",""))
         synchronizer.sync()
         print_info("模型同步完成")

     

 
def init():
    sync_models()
    init_user(DB)

if __name__ == '__main__':
    init()
