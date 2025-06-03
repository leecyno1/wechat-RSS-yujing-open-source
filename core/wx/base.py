import requests
import json
from core.models import Feed

from core.db import DB
from core.models.feed import Feed
from core.config import Config
from core.config import cfg
# 定义基类
class WxGather:
    articles=[]
    def all_count(self):
        if getattr(self, 'articles', None) is not None:
            return len(self.articles)
        return 0
    def Model(self):
        if cfg.get("model","web")=="web":
            from core.wx import MpsWeb
            wx=MpsWeb()
        else:
            from core.wx import MpsApi
            wx=MpsApi()
        return wx
    def __init__(self,is_add:bool=False):
         
        self.is_add=is_add
        self.headers = {
            "Cookie": cfg.get('cookie', ''),
            "User-Agent": cfg.get('user_agent', '') 
        }
        self.user_agent = cfg.get('user_agent', '')
        self.cookies = cfg.get('cookie', '')
        self.token=cfg.get('token','')
        self.Gather_Content=cfg.get('gather_content',False)
        session=  requests.Session()
        timeout = (5, 10)
        session.timeout = timeout
        self.session=session
    def FillBack(self,CallBack=None,data=None,Ext_Data=None):
        if CallBack is not None:
            if data is not  None:
                from core.models import Article
                from datetime import datetime
                art={
                    "id":str(data['id']),
                    "mp_id":data['mp_id'],
                    "title":data['title'],
                    "url":data['link'],
                    "pic_url":data['cover'],
                    "content":data['content'],
                    "publish_time":data['update_time'],
                }
                if CallBack(art):
                    art["ext"]=Ext_Data
                    art.pop("content")
                    self.articles.append(art)


    #通过公众号码平台接口查询公众号
    def search_Biz(self,kw:str="",limit=5,offset=0):
        url = "https://mp.weixin.qq.com/cgi-bin/searchbiz"
        params = {
            "action": "search_biz",
            "begin":offset,
            "count": limit,
            "query": kw,
            "token":  self.token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1"
        }
    
        headers = {
            "Cookie": self.cookies,
            "User-Agent":self.user_agent
        }
        data={}
        try:
            response = requests.get(
            url,
            params=params,
            headers=headers,
            )
            response.raise_for_status()  # 检查状态码是否为200
            data = response.text  # 解析JSON数据
            data = json.loads(data)  # 手动解析
            if 'publish_page' in data:
                data['publish_page']=json.loads(data['publish_page'])
        except Exception as e:
            print(f"请求失败: {e}")
            return None
        return data
    
    
    
    def Start(self,mp_id=None):
        print(f"开始")
        import time
        self.update_mps(mp_id,Feed(
          sync_time=int(time.time()),
          update_time=int(time.time()),
        ))

    def Item_Over(self,item=None):
        print(f"item end")
        pass
    def Error(self,error:str):
        self.Over()
        raise Exception(error)
        print("错误")
    def Over(self,data=None):
        if getattr(self, 'articles', None) is not None:
            print(f"成功{len(self.articles)}条")


    def dateformat(self,timestamp:any):
        from datetime import datetime, timezone
        # UTC时间对象
        utc_dt = datetime.fromtimestamp(int(timestamp), timezone.utc)
        t=(utc_dt.strftime("%Y-%m-%d %H:%M:%S")) 

        # UTC转本地时区
        local_dt = utc_dt.astimezone()
        t=(local_dt.strftime("%Y-%m-%d %H:%M:%S"))
        return t

    # 更新公众号更新状态
    def update_mps(self,mp_id:str, mp:Feed):
        """更新公众号同步状态和时间信息
        Args:
            mp_id: 公众号ID
            mp: Feed对象，包含公众号信息
        """
        from datetime import datetime
        import time
        try:
            
            # 更新同步时间为当前时间
            current_time = int(time.time())
            update_data = {
                'sync_time': current_time,
                # 'updated_at': dateformat(current_time)
                'updated_at': datetime.now(),
            }
            
            # 如果有新文章时间，也更新update_time
            if hasattr(mp, 'update_time') and mp.update_time:
                update_data['update_time'] = mp.update_time
            if hasattr(mp,'status') and mp.status is not None:
                update_data['status']=mp.status

            # 获取数据库会话并执行更新
            session = DB.get_session()
            try:
                feed = session.query(Feed).filter(Feed.id == mp_id).first()
                if feed:
                    for key, value in update_data.items():
                        print(f"更新公众号{mp_id}的{key}为{value}")
                        setattr(feed, key, value)
                    session.commit()
                else:
                    print(f"未找到ID为{mp_id}的公众号记录")
            finally:
                session.close()
                
        except Exception as e:
            print(f"更新公众号状态失败: {e}")
            raise NotImplementedError("Subclasses should implement this method.")