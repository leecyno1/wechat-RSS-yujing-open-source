from os import remove
from driver.wxarticle import Web
from driver.success import Success
from driver.base import WX_API
from core.print import print_error,print_info,print_success
from jobs.fetch_no_article import fetch_articles_without_content
import base64
import re


def testWeb():
    urls="""
    https://mp.weixin.qq.com/s/puc5q9xFmfMSy3OyqeYxZA
    """.strip().split("\n")

    Web.FixArticle(urls=urls)
    pass

def testWx_Api():
      # 测试代码
    def login_success_callback(session_data, account_info):
        print("登录成功！")
        print(f"Token: {session_data.get('token')}")
        print(f"账号信息: {account_info}")
    
    def notice_callback(message):
        print(f"通知: {message}")
    
    from driver.wx_api import WeChat_api 
    # 保持程序运行以等待登录
    # 使用token登录
    haLogin=WeChat_api.login_with_token()
    if haLogin:
        print("已登录")
    else:
        print("未登录")

    # 获取二维码
    # result = get_qr_code(login_success_callback, notice_callback)
    result=WeChat_api.GetCode(login_success_callback, notice_callback)
    # print(f"二维码结果: {result}")


def testMarkDown():
    from core.models import Article
    from core.db import DB
    session=DB.get_session()
    art=session.query(Article).filter(Article.content != None).order_by(Article.id.desc()).first()
    # print(art.content)
    from core.content_format import  format_content
    content= format_content(art.content,"markdown")
    return content

def testMd2Doc():
    from tools.mdtools.export import export_md_to_doc
    doc_id="3918391364-2247502779_3,3076560530-2673097250_1,3076560530-2673097167_1,3076560530-2673097166_1".split(",")
    export_md_to_doc(mp_id="MP_WXS_3918391364",doc_id=doc_id,export_md=True, zip_file=False,remove_images=False,remove_links=False)



def testToken():
    from driver.auth import auth
    auth()
    # input("按任意键退出")

def testLogin():
    from driver.wx import WX_API
    from driver.success import Success
    # de_url=WX_API.Token(Success)
    # de_url=WX_API.GetCode(Success)
    # de_url=WX_API.wxLogin()
    # print(de_url)
    input("按任意键退出")
def testNotice():
    from jobs.notice import sys_notice
    text="""
    消息测试<font color="warning">132例</font>，请相关同事注意。
> 类型:<font color="comment">用户反馈</font>
> 普通用户反馈:<font color="comment">117例</font>
> VIP用户反馈:<font color="comment">15例</font>
"""
    sys_notice(text,"测试通知","测试通知","测试通知")

def test_fetch_articles_without_content():
    from jobs.fetch_no_article import fetch_articles_without_content,start_sync_content
    fetch_articles_without_content()
    start_sync_content()
    input("按任意键退出")
def test_Gather_Article():
    from core.wx.base import WxGather
    ga=WxGather().Model("web")
    urls=[
        "https://mp.weixin.qq.com/s/puc5q9xFmfMSy3OyqeYxZA",
        #   "https://mp.weixin.qq.com/s/r8AgtesEVSnV-QpEbpb8-Q",
        #   "https://mp.weixin.qq.com/s?__biz=MzI3MTQzNjYxNw==&mid=2247912631&idx=1&sn=6a60ca17a85b2aac8c1236c9df8cbe36&scene=21&poc_token=HNMGC2mj1itdGEMeEq01KxIvG5QUmsY-ZUxsdewX"
        ]
    for url in urls:
        content= ga.content_extract(url)
        print(content)


def test_screenshot():
    from playwright.sync_api import sync_playwright,TimeoutError
    playwright=sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # 导航到目标页面
    page.goto('https://mp.weixin.qq.com/')  # 替换为实际的目标URL
    # 定义一个标志来指示是否已经找到目标URL
    
    # 等待页面加载完成
    # 查找图片元素
    image_element = page.query_selector('.login__type__container__scan__qrcode')  # 替换为实际的图片src属性值
    path='./static/qrcode.png'
    target_substring="home"
    if image_element:
        # 截图保存
        image_element.screenshot(path=path)
        print(f'图片已成功截取并保存为 {path}')
    else:
        print('未找到指定的图片元素')
       
    navigation_completed = False

    # # 监听页面导航事件
    def handle_frame_navigated(frame):
        nonlocal navigation_completed
        current_url = frame.url
        if target_substring in current_url and not navigation_completed:
            print(f"页面已成功跳转到包含 '{target_substring}' 的URL: {current_url}")
            navigation_completed = True
    page.on('framenavigated', handle_frame_navigated)
    page.wait_for_event("framenavigated")
    print(page.url)
    # 关闭浏览器
    context.close()
    browser.close()



if __name__=="__main__":
    # testLogin()

    # test_screenshot()
    # test_Gather_Article()
    testWx_Api()
    # test_fetch_articles_without_content()
    # testWeb()
    # testNotice()
    # testMd2Doc()
    # testToken()
    # testMarkDown()
