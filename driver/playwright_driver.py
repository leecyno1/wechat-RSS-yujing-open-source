import os
import platform
from socket import timeout
import subprocess
import sys
import json
import random
import uuid


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("检测到playwright未安装，正在自动安装...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    print("playwright安装完成，正在安装浏览器...")
    
    # 检查是否设置了自定义浏览器安装路径
    browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH","./data/driver/")
    if browsers_path:
        print(f"使用自定义浏览器安装路径: {browsers_path}")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "--with-deps"], env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers_path})
    else:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "--with-deps"])
    
    from playwright.sync_api import sync_playwright

class PlaywrightController:
    def __init__(self):
        self.system = platform.system().lower()
        self.driver = None
        self.browser = None
        self.context = None
        self.page = None
        self.isClose = True
       
    def string_to_json(self, json_string):
        try:
            json_obj = json.loads(json_string)
            return json_obj
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            return ""

    def parse_string_to_dict(self, kv_str: str):
        result = {}
        items = kv_str.strip().split(';')
        for item in items:
            try:
                key, value = item.strip().split('=')
                result[key.strip()] = value.strip()
            except Exception as e:
                pass
        return result

    def add_cookies(self, cookies):
        if self.context is None:
            raise Exception("浏览器未启动，请先调用 start_browser()")
        for cookie in cookies:
            self.context.add_cookies([cookie])

    def add_cookie(self, cookie):
        if self.context is None:
            raise Exception("浏览器未启动，请先调用 start_browser()")
        self.context.add_cookies([cookie])

    def get_cookies(self, url=None):
        """获取当前页面的cookies"""
        if self.context is None:
            raise Exception("浏览器未启动，请先调用 start_browser()")
        
        if url:
            # 获取指定URL的cookies
            return self.context.cookies(url)
        else:
            # 获取所有cookies
            return self.context.cookies()


    def _get_anti_crawler_config(self, mobile_mode=False):
        """获取反爬虫配置"""
        
        # 生成随机指纹
        fingerprint = self._generate_uuid()
        
        # 基础配置
        config = {
            "user_agent": self._get_realistic_user_agent(mobile_mode),
            "viewport": {
                "width": random.randint(1200, 1920) if not mobile_mode else 375,
                "height": random.randint(800, 1080) if not mobile_mode else 812,
                "device_scale_factor": random.choice([1, 1.25, 1.5, 2])
            },
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1"
            }
        }
        
        # 移动端特殊配置
        if mobile_mode:
            config["extra_http_headers"].update({
                "User-Agent": config["user_agent"],
                "X-Requested-With": "com.tencent.mm"
            })
        
        return config

    def _get_realistic_user_agent(self, mobile_mode=False):
        """获取更真实的User-Agent"""
        print(f"浏览器特征设置完成: {'移动端' if mobile_mode else '桌面端'}")
        if mobile_mode:
            # 移动端User-Agent
            mobile_agents = [
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
                "Mozilla/5.0 (Windows Phone 10.0; Android 6.0.1; Microsoft; Lumia 950) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36 Edge/14.14393"
            ]
            return random.choice(mobile_agents)
        else:
            # 桌面端User-Agent（更新版本）
            desktop_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
            return random.choice(desktop_agents)

    def _generate_uuid(self):
        """生成UUID指纹"""
        return str(uuid.uuid4()).replace("-", "")

    def _apply_anti_crawler_scripts(self):

        try:
            from playwright_stealth.stealth import Stealth
        except:
            print("检测到playwright未安装，正在自动安装...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright_stealth"])
        
        stealth = Stealth()
        stealth.apply_stealth_sync(self.page)
        """应用反爬虫脚本"""
        # 隐藏自动化特征
        self.page.add_init_script("""
        // 隐藏webdriver属性
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
        
        // 隐藏chrome属性
        Object.defineProperty(window, 'chrome', {
            get: () => false,
        });
        
        // 修改plugins长度
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // 修改languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en'],
        });
        
        // 隐藏自动化痕迹
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
        
        // 修改permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """)
        
        # 设置更真实的浏览器行为
        self.page.evaluate("""
        // 随机延迟点击事件
        const originalAddEventListener = EventTarget.prototype.addEventListener;
        EventTarget.prototype.addEventListener = function(type, listener, options) {
            if (type === 'click') {
                const wrappedListener = function(...args) {
                    setTimeout(() => listener.apply(this, args), Math.random() * 100 + 50);
                };
                return originalAddEventListener.call(this, type, wrappedListener, options);
            }
            return originalAddEventListener.call(this, type, listener, options);
        };
        
        // 随机化鼠标移动
        document.addEventListener('mousemove', (e) => {
            if (Math.random() > 0.7) {
                e.stopImmediatePropagation();
            }
        }, true);
        """)

       

    import os
    def start_browser(self, headless=True, mobile_mode=False, dis_image=False, browser_name="firefox", language="zh-CN", anti_crawler=True):
        try:
            if  bool(os.getenv("NOT_HEADLESS",False)):
                headless = False
            if self.driver is None:
                self.driver = sync_playwright().start()
           
            # 根据浏览器名称选择浏览器类型
            if browser_name.lower() == "firefox":
                browser_type = self.driver.firefox
            elif browser_name.lower() == "webkit":
                browser_type = self.driver.webkit
            else:
                browser_type = self.driver.chromium  # 默认使用chromium
            self.browser = browser_type.launch(headless=headless)
            
            # 设置浏览器语言为中文
            context_options = {
                "locale": language
            }
            
            # 反爬虫配置
            if anti_crawler:
                context_options.update(self._get_anti_crawler_config(mobile_mode))
            
            self.context = self.browser.new_context(**context_options)
            self.page = self.context.new_page()
           

            if mobile_mode:
                self.page.set_viewport_size({"width": 375, "height": 812})
            # else:
            #     self.page.set_viewport_size({"width": 1920, "height": 1080})

            if not dis_image:
                self.context.route("**/*.{png,jpg,jpeg}", lambda route: route.abort())

            # 应用反爬虫脚本
            if anti_crawler:
                self._apply_anti_crawler_scripts()

            self.isClose = False
            return self.page
        except Exception as e:
            print(f"浏览器启动失败: {str(e)}")
            self.cleanup()
            raise

    def __del__(self):
        # 避免在程序退出时调用Close()，防止"can't register atexit after shutdown"错误
        try:
            import atexit
            # 检查是否在atexit处理过程中
            if not atexit._exithandlers:
                self.Close()
        except:
            # 如果发生任何异常，直接跳过清理
            pass

    def open_url(self, url,wait_until="domcontentloaded"):
        try:
            self.page.goto(url,wait_until=wait_until)
        except Exception as e:
            raise Exception(f"打开URL失败: {str(e)}")

    def Close(self):
        self.cleanup()

    def cleanup(self):
        """清理所有资源"""
        try:
            if hasattr(self, 'page') and self.page:
                self.page.close()
            if hasattr(self, 'context') and self.context:
                self.context.close()
            if hasattr(self, 'browser') and self.browser:
                self.browser.close()
            if hasattr(self, 'playwright') and self.driver:
                self.driver.stop()
            self.isClose = True
        except Exception as e:
            print(f"资源清理失败: {str(e)}")

    def dict_to_json(self, data_dict):
        try:
            return json.dumps(data_dict, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as e:
            print(f"字典转JSON失败: {e}")
            return ""

ControlDriver=PlaywrightController()
# 示例用法
if __name__ == "__main__":
    controller = PlaywrightController()
    try:
        controller.start_browser()
        controller.open_url("https://mp.weixin.qq.com/")
    finally:
        # controller.Close()
        pass