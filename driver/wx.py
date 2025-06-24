import sys
from .firefox_driver import FirefoxController
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
from .success import Success
from selenium.webdriver.common.action_chains import ActionChains
import time
import os
import re
from threading import Thread
from threading import Timer
import json
from core.print import print_error
class Wx:
    HasLogin=False
    SESSION=None
    HasCode=False
    isLOCK=False
    WX_LOGIN="https://mp.weixin.qq.com/"
    WX_HOME="https://mp.weixin.qq.com/cgi-bin/home"
    wx_login_url="static/wx_qrcode.png"
    def check_dependencies(self):
        """检查必要的依赖包"""
        try:
            import selenium
            import PIL
        except ImportError as e:
            print("缺少必要的依赖包，请先安装：")
            print("pip install selenium Pillow")
            return False
        return True
    def GetHasCode(self):
        if os.path.exists(self.wx_login_url):
            return True
        return False
    def extract_token_from_requests(self,driver):
        """从页面中提取token"""
        try:
            # 尝试从当前URL获取token
            current_url = driver.current_url
            token_match = re.search(r'token=([^&]+)', current_url)
            if token_match:
                return token_match.group(1)
            
            # 尝试从localStorage获取
            token = driver.execute_script("return localStorage.getItem('token');")
            if token:
                return token
                
            # 尝试从sessionStorage获取
            token = driver.execute_script("return sessionStorage.getItem('token');")
            if token:
                return token
                
            # 尝试从cookie获取
            cookies = driver.get_cookies()
            for cookie in cookies:
                if 'token' in cookie['name'].lower():
                    return cookie['value']
                    
            return None
        except Exception as e:
            print(f"提取token时出错: {str(e)}")
            return None
    def GetCode(self,CallBack=None):
        if  self.isLock():
            return {"code":self.wx_login_url,"msg":"微信公众平台登录脚本正在运行，请勿重复运行！"}
        print("子线程执行中")
        self.thread = Thread(target=self.wxLogin,args=(CallBack,))  # 传入函数名
        self.thread.start()  # 启动线程
        print("微信公众平台登录 v1.34")
        return WX_API.QRcode()
    wait_time=100
    def QRcode(self):
        return {
            "code":self.wx_login_url
        }
    def refresh_task(self):
        try:
            self.controller.driver.refresh()
            self.Call_Success()
            # 检查登录状态
            if "home" not in self.controller.driver.current_url:
                print("检测到登录已过期，请重新登录")
                raise Exception(f"登录已经失效，请重新登录")
        except Exception as e:
            raise Exception(f"浏览器关闭")  # 重新抛出异常以便外部捕获处理

    def schedule_refresh(self,interval=60):
        if interval <= 0:
            return
        if self.HasLogin:
            try:
                self.refresh_task()
                Timer(interval, self.schedule_refresh).start()
            except Exception as e:
                raise Exception(f"浏览器已经关闭")
    def Token(self):
        if 'controller' not in locals():
            controller = FirefoxController()
            self.controller=controller
        self.controller.start_browser()
        self.controller.open_url(self.WX_HOME)
        self.schedule_refresh()
    def isLock(self):             
        if self.isLock:
            if os.path.exists(self.wx_login_url):
                try:
                    size=os.path.getsize(self.wx_login_url)
                    return size>364
                except Exception as e:
                    print(f"二维码图片获取失败: {str(e)}")
                    return False
            else:
                print("二维码图片不存在，请重新获取")
                return False
        return self.isLock
    def wxLogin(self,CallBack=None,NeedExit=False, refresh_interval=60):
        """
        微信公众平台登录流程：
        1. 检查依赖和环境
        2. 打开微信公众平台
        3. 全屏截图保存二维码
        4. 等待用户扫码登录
        5. 获取登录后的cookie和token
        6. 启动定时刷新线程(默认30分钟刷新一次)
        """
        # 检查依赖
        if not self.check_dependencies():
            return None
        
        try:
            if  self.isLOCK:
                return "微信公众平台登录脚本正在运行，请勿重复运行！"
            self.HasLogin=False
            self.isLOCK=True
            self.Clean()
            self.Close()
            # 初始化浏览器控制器
            controller = FirefoxController()
            self.controller=controller
            # 启动浏览器并打开微信公众平台
            print("正在启动浏览器...")
            controller.start_browser()
            controller.open_url(self.WX_LOGIN)
            
            # 等待页面完全加载
            print("正在加载登录页面...")
              # 等待登录后首页完全加载
            wait = WebDriverWait(controller.driver, self.wait_time)
              # 然后等待其中的图片加载完成
            wait.until(lambda d: d.execute_script(
                "return document.querySelector('img').complete"))
            time.sleep(2)
            
            # 滚动到二维码区域
            qrcode = controller.driver.find_element(By.CLASS_NAME, "login__type__container__scan__qrcode")
            ActionChains(controller.driver).move_to_element(qrcode).perform()
            wait = WebDriverWait(controller.driver, self.wait_time)
            # 确保二维码可见
            wait = WebDriverWait(controller.driver, self.wait_time)
            wait.until(EC.visibility_of(qrcode))
            # 全屏截图并裁剪二维码区域
            print("正在生成二维码图片...")
            controller.driver.save_screenshot("temp_screenshot.png")
            img = Image.open("temp_screenshot.png")
            
            # 获取二维码位置和尺寸
            location = qrcode.location
            size = qrcode.size
            left = location['x']
            top = location['y']
            right = location['x'] + size['width']
            bottom = location['y'] + size['height']
            
            # 裁剪并保存二维码
            img = img.crop((left, top, right, bottom))
            img.save(self.wx_login_url)
            os.remove("temp_screenshot.png")
            
            print("二维码已保存为 wx_qrcode.png，请扫码登录...")
            self.HasCode=True
            if os.path.getsize(self.wx_login_url)<=364:
                raise Exception("二维码图片获取失败，请重新扫码")
            # 等待登录成功（检测二维码图片加载完成）
            print("等待扫码登录...")
            wait = WebDriverWait(controller.driver, 120)
            wait.until(EC.url_contains(self.WX_HOME))
            self.CallBack=CallBack
          
            
            self.Call_Success()
            
            self.schedule_refresh(interval=refresh_interval)
        except NameError as e:
            # 修正此处，确保异常处理逻辑正确
            print_error(f"\n错误发生: {str(e)}")
            self.SESSION = None  # 发生错误时设置 SESSION 为 None
            return self.SESSION  # 异常处理后不需要返回
        except Exception as e:
            print(f"\n错误发生: {str(e)}")
            print("可能的原因:\n1. 请确保已安装Firefox浏览器\n2. 请确保geckodriver已下载并配置到PATH中\n3. 检查网络连接是否可以访问微信公众平台")
            self.SESSION=None
            self.Close()
        finally:
            self.isLOCK=False
            if 'controller' in locals() and NeedExit:
                self.Clean()
                controller.close()
        return self.SESSION
    def Call_Success(self):
        print("登录成功！")
        self.HasLogin=True
        # 获取token
        token = self.extract_token_from_requests(self.controller.driver)
        
        # 获取当前所有cookie
        cookies = self.controller.driver.get_cookies()
        # print("\n获取到的Cookie:")
        cookies_str=""
        for cookie in cookies:
            # print(f"{cookie['name']}={cookie['value']}")
            cookies_str+=f"{cookie['name']}={cookie['value']}; "
        if token:
            print(f"\nToken: {token}")
        
        # 计算 slave_sid cookie 有效时间
        cookie_expiry = None
        for cookie in cookies:
            if cookie['name'] == 'slave_sid' and 'expiry' in cookie:
                try:
                    expiry_time = float(cookie['expiry'])
                    remaining_time = expiry_time - time.time()
                    if remaining_time > 0:
                        cookie_expiry = {
                            'expiry_timestamp': expiry_time,
                            'remaining_seconds': int(remaining_time),
                            'expiry_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry_time))
                        }
                    break
                except ValueError:
                    print(f"slave_sid 的过期时间戳无效: {cookie['expiry']}")
                    break

        self.SESSION= {
            'cookies': cookies,
            'cookies_str': cookies_str,
            'token': token,
            'wx_login_url': self.wx_login_url,
            'expiry': cookie_expiry
        }
        self.HasLogin=True
        # print(cookie_expiry)
        if self.CallBack is not None:
            self.CallBack(self.SESSION)
        return self.SESSION 
    
    def Close(self):
        rel=False
        try:
                self.controller.close()
                rel=True
        except:
            print("浏览器未启动")
            pass
        return rel
    def Clean(self):
        try:
            os.remove(self.wx_login_url)
        except:
            pass
        finally:
           pass
           
    def expire_all_cookies(self):
        """设置所有cookie为过期状态"""
        try:
            if hasattr(self, 'controller') and hasattr(self.controller, 'driver'):
                self.controller.driver.delete_all_cookies()
                return True
            else:
                print("浏览器未启动，无法操作cookie")
                return False
        except Exception as e:
            print(f"设置cookie过期时出错: {str(e)}")
            return False
WX_API = Wx()