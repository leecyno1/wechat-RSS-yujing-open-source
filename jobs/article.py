
import core.wx as wx 
import core.db as db
from core.config import DEBUG,cfg
from core.models.article import Article
# 初始化数据库
wx_db=db.Db()    
wx_db.init(cfg.get("db"))
def delete_article(id:str):
    try:
        session=wx_db.session
        article = session.query(Article).filter(Article.id == id).first()
        session.delete(article)
        session.commit()
    except Exception as e:
        print(e)
        pass



def UpdateArticle(art:dict):
    mps_count=0
    if DEBUG:
        delete_article(art['id'])
        pass
    if  wx_db.add_article(art):
        mps_count=mps_count+1
        return True
    return False
