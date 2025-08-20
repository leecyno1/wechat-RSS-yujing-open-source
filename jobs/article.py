
import core.wx as wx 
import core.db as db
from core.config import DEBUG,cfg
from core.models.article import Article

DB=db.Db(tag="文章采集API")

def UpdateArticle(art:dict):
    mps_count=0
    if DEBUG:
        # DB.delete_article(art)
        pass
    if  DB.add_article(art):
        mps_count=mps_count+1
        return True
    return False
def Update_Over(data=None):
    print("更新完成",data)
    pass