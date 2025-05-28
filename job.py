import schedule, time
import core.wx as wx 
import core.db as db
from core.config import DEBUG,cfg

import random
import core.log as log
from datetime import datetime

logger=log.logger

# 初始化数据库
wx_db=db.Db()    
wx_db.init(cfg.get("db"))
from core.models.article import Article
def delete_article(id:str):
    try:
        session=wx_db.session
        article = session.query(Article).filter(Article.id == id).first()
        session.delete(article)
        session.commit()
    except Exception as e:
        print(e)
        pass
# 获取公众号列表
mps=wx_db.get_all_mps()
def do_job():
    print("开始更新")
    all_count=0
    text=f" **时间**：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n"
    for item in mps:
        text_list=""
        # 成功更新数量计数
        mps_count=0
        faker_id=item.faker_id
        mp_id=item.id
        print(f'正在更新公众号：{item.mp_name}({item.id})')
            # 获取对应公众号列表
        data=wx.get_list(faker_id,mp_id,0)
        for art in data:
            # 添加到数据库
            if DEBUG:
                delete_article(art['id'])
            if  wx_db.add_article(art):
                mps_count=mps_count+1
                text_list+=f"{mps_count}. [{art['title']}](https://mp.weixin.qq.com/s/{art['id']})[{art['created_at']}]\n"

        logger.info(f"{item.mp_name} 更新结束,共更新{mps_count}")
        text+=f"+ **{item.mp_name}**({mps_count})\n{text_list}"
        all_count=all_count+mps_count

        # 随机休眠 防止被封锁
        # if not cfg.DEBUG:
        #     time.sleep(random.randint(2,5))
    logger.info(f"所有公众号更新完成,共更新{all_count}条数据")
    text+=f"\n所有公众号更新完成,共更新{all_count}条数据"
    if all_count>0:
        send_notice(text,cfg.get('app_name',default='we-mp-rss'))
    else:
        print(text)    
def start():
    schedule.every(int(cfg.get("interval",5*60))).seconds.do(do_job)  # 默认5分钟执行一次
    # schedule.every.day.at("08:00").do(job)  # 每天8点执行
    while True:
        schedule.run_pending()
        time.sleep(10)

def send_notice(text:str="",title:str=""):
    markdown_text = f"### {title} 通知\n{text}"
    webhook = cfg.get('notice')['dingding']
    # 修正参数顺序
    from core.notice import notice
    notice(webhook, title, markdown_text)

if __name__ == '__main__':
    do_job()