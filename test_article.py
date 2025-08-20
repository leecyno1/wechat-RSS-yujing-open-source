from driver.wxarticle import Web
from driver.success import Success
from driver.wx import WX_API
from core.print import print_error,print_info,print_success
from jobs.fetch_no_article import fetch_articles_without_content
def testWeb():
    # 示例用法
    try:
        # fetch_articles_without_content()
        urls=[
            "https://mp.weixin.qq.com/s/lAMajfW2jN5rcFNzgXJ4Sg",
            # "https://mp.weixin.qq.com/s/roc7CmIjuEyqlMgUYRF9dw",
            # "https://mp.weixin.qq.com/s/yNL6jIHjvbNCH5VRgWpf-w",
            # "https://mp.weixin.qq.com/s/irJfYFP4TBVb4rD8jFxBoA",
            # "https://mp.weixin.qq.com/s/SJNb4YfqhlArFdCWhtKmXg",
            # "https://mp.weixin.qq.com/s/_7owCGjJ1mVaYH9NMPX1TQ",
            # "https://mp.weixin.qq.com/s/zmhHRTV2S2ZCr2fYPIg5wA",
        ]
        for url in urls:
            Web.Close()
            article_data = Web.get_article_content(url)
            del article_data['content']
            print_success(article_data)
        # Web.Close()
        
        # WX_API.wxLogin(CallBack=Success)
        # WX_API.Token(CallBack=Success)
        # input("按任意键退出")
    except Exception as e:
        print_error(f"错误: {e}")  

def testMarkDown():
    from core.models import Article
    from core.db import DB
    session=DB.get_session()
    art=session.query(Article).filter(Article.content != None).order_by(Article.id.desc()).first()
    # print(art.content)
    from core.content_format import  format_content
    print(format_content(art.content,"markdown"))
    pass
def testToken():
    from driver.auth import auth
    auth()
    # input("按任意键退出")
if __name__=="__main__":
    # testWeb()
    testToken()
    # testMarkDown()