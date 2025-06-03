from datetime import datetime
from core.models.article import Article
from .article import UpdateArticle
import core.db as db
from core.wx import WxGather
from core.log import logger
from core.task import TaskScheduler
from core.models.feed import Feed
from core.config import cfg
wx_db=db.Db()
wx_db.init(cfg.get("db"))
def fetch_all_article():
    print("开始更新")
    wx=WxGather().Model()
    try:
        # 获取公众号列表
        mps=db.DB.get_all_mps()
        for item in mps:
            try:
                wx.get_Articles(item.faker_id,CallBack=UpdateArticle,Mps_id=item.id,Mps_title=item.mp_name, MaxPage=1)
            except Exception as e:
                print(e)
        print(wx.articles) 
    except Exception as e:
        print(e)         
    finally:
        logger.info(f"所有公众号更新完成,共更新{wx.all_count()}条数据")


def test(info:str):
    print("任务测试成功",info)

from core.models.message_task import MessageTask
# from core.queue import TaskQueue
def add_job(mps:list[Feed]=None):
        # TaskQueue.add_task(test,info=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # print("执行任务", task.mps_id)
        print("执行任务")
        wx=WxGather().Model()
        for item in mps:
            try:
                wx.get_Articles(item.faker_id,CallBack=UpdateArticle,Mps_id=item.id,Mps_title=item.mp_name, MaxPage=1)
            except Exception as e:
                print(e)
        print(wx.articles) 

import json
def get_feeds(task:MessageTask=None):
     mps = json.loads(task.mps_id)
     ids=",".join([item["id"]for item in mps])
     mps=wx_db.get_mps_list(ids)
     return mps
scheduler=TaskScheduler()
def start_job():
    from .taskmsg import get_message_task
    tasks=get_message_task()
    if not tasks:
        print("没有任务")
        return
    for task in tasks:
        cron_exp=task.cron_exp
        # cron_exp="*/1 * * * *"
        cron_exp="* * * * * *"
        job_id=scheduler.add_cron_job(add_job,cron_expr=cron_exp,args=[get_feeds(task)])
        print(f"已添加任务: {job_id}")
    scheduler.start()
    print("启动任务")

if __name__ == '__main__':
    # do_job()
    # start_job()
    pass