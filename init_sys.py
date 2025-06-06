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
def init_user(_db: Db):
    try:
      username,password=os.getenv("USERNAME", "admin"),os.getenv("PASSWORD", "admin@123")
      session=_db.get_session()
      session.merge(User(
          id=0,
          username=username,
          password_hash=pwd_context.hash(password),
          ))
      session.commit()
    except Exception as e:
        # print_error(f"Init error: {str(e)}")
        pass
def sync_models():
     # 同步模型到表结构
         from core.data_sync import ModelSync
         DB.create_tables()
         ModelSync(eng=DB.get_engine())
         print_info("模型同步完成")

     

 
def init():
    sync_models()
    init_user(DB)

if __name__ == '__main__':
    init()