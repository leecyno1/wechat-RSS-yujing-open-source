from .firefox_driver import FirefoxController
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Dict
from core.print import print_error,print_info,print_success,print_warning
import time
import re

class WXArticleFetcher:
    """微信公众号文章获取器
    
    基于WX_API登录状态获取文章内容
    
    Attributes:
        wait_timeout: 显式等待超时时间(秒)
    """
    
    def __init__(self, wait_timeout: int = 10):
        """初始化文章获取器"""
        self.wait_timeout = wait_timeout
        self.controller = FirefoxController()
        if not self.controller:
            raise Exception("WebDriver未初始化或未登录")
       
        
    def extract_biz_from_source(self,url:str) -> str:
        """从URL或页面源码中提取biz参数
        
        1. 首先尝试从URL参数中提取__biz
        2. 如果URL中没有，则从页面源码中提取
        """
        # 尝试从URL中提取
        match = re.search(r'[?&]__biz=([^&]+)', url)
        if match:
            return match.group(1)
            
        # 从页面源码中提取
        try:
            # 从页面源码中查找biz信息
            page_source = self.driver.page_source
            biz_match = re.search(r'var biz = "([^"]+)"', page_source)
            if biz_match:
                return biz_match.group(1)
                
            # 尝试其他可能的biz存储位置
            biz_match = re.search(r'window\.__biz=([^&]+)', page_source)
            if biz_match:
                return biz_match.group(1)
                
            return ""
            
        except Exception:
            return ""
        
    def get_article_content(self, url: str) -> Dict:
        """获取单篇文章详细内容
        
        Args:
            url: 文章URL (如: https://mp.weixin.qq.com/s/qfe2F6Dcw-uPXW_XW7UAIg)
            
        Returns:
            文章内容数据字典，包含:
            - title: 文章标题
            - author: 作者
            - publish_time: 发布时间
            - content: 正文HTML
            - images: 图片URL列表
            
        Raises:
            Exception: 如果未登录或获取内容失败
        """
        info={
                "title": "",
                "publish_time": "",
                "content": "",
                "images": "",
                "mp_info":{
                "mp_name":"",   
                "logo":"",
                "biz": "",
                }
            }
        self.controller.start_browser()    
        self.driver = self.controller.driver
        print_warning(f"Get:{url} Wait:{self.wait_timeout}")
        self.controller.open_url(url)
        driver=self.driver
        wait = WebDriverWait(driver, self.wait_timeout)
        try:
           
            driver.get(url)
              # 等待页面加载
            body=driver.find_element(By.TAG_NAME,"body").text
            info["content"]=body
            if "该内容已被发布者删除" in body or "The content has been deleted by the author." in body:
                info["content"]="DELETED"
                raise Exception("该内容已被发布者删除")
            if  "内容审核中" in body:
                info['content']="DELETED"
                raise Exception("内容审核中")
            # 等待关键元素加载
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#activity-detail"))
            )
            print(body)
             # 等待页面加载完成，并查找 meta[property="og:title"]
            og_title = wait.until(EC.presence_of_element_located((By.XPATH, '//meta[@property="og:title"]')))
            
            # 获取属性值
            print(og_title.get_attribute("content"))
            # 获取文章元数据
            title = og_title.get_attribute("content")

            author = driver.find_element(
                By.CSS_SELECTOR, "#meta_content .rich_media_meta_text"
            ).text.strip()
            
            publish_time = driver.find_element(
                By.CSS_SELECTOR, "#publish_time"
            ).text.strip()
            
            # 获取正文内容和图片
            content_element = driver.find_element(
                By.CSS_SELECTOR, "#js_content"
            )
            content = content_element.get_attribute("innerHTML")
            
            images = [
                img.get_attribute("data-src") or img.get_attribute("src")
                for img in content_element.find_elements(By.TAG_NAME, "img")
                if img.get_attribute("data-src") or img.get_attribute("src")
            ]
            info["title"]=title
            info["author"]=author
            info["publish_time"]=publish_time
            info["content"]=content
            info["images"]=images

        except Exception as e:
            # raise Exception(f"文章内容获取失败: {str(e)}")
            print(f"文章内容获取失败: {str(e)}")
            print_warning(f"\n\n{body}")
            # raise

        try:
            # 等待关键元素加载
            wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "wx_follow_avatar"))
            )
            # 查找<div class="wx_follow_hd">元素
            ele_logo = driver.find_element(By.CLASS_NAME, 'wx_follow_avatar').find_element(By.TAG_NAME, 'img')
            # 获取<img>标签的src属性
            logo_src = ele_logo.get_attribute('src')
            ele_name = driver.find_element(By.CLASS_NAME, 'wx_follow_bd')
            title= ele_name.text
            info["mp_info"]={
                "mp_name":title,
                "logo":logo_src,
                "biz": self.extract_biz_from_source(url), 
            }
        except Exception as e:
            # raise Exception(f"文章内容获取失败: {str(e)}")
            # print(f"获取公众号信息失败: {str(e)}")    
            pass
        self.Close()
        return info
    def Close(self):
        """关闭浏览器"""
        if hasattr(self, 'controller'):
            self.controller.Close()
        else:
            print("WXArticleFetcher未初始化或已销毁")
    def __del__(self):
        """销毁文章获取器"""
        if hasattr(WXArticleFetcher, 'controller'):
            WXArticleFetcher.controller.close()
Web=WXArticleFetcher()