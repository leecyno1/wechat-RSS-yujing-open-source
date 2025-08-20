import os
import platform
import subprocess
import sys
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
from selenium.common.exceptions import WebDriverException
import json
class FirefoxController:
    isClose=True
    def __init__(self):
        self.system = platform.system().lower()
        self.driver_path = None
        self.browser_path = None
        self.options = Options()
        
        # 设置跨平台兼容的默认选项
        self.options.set_preference("dom.webnotifications.enabled", False)
        self.options.set_preference("dom.push.enabled", False)
    def string_to_json(self,json_string):
        try:
            json_obj = json.loads(json_string)
            return json_obj
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            return ""
    def parse_string_to_dict(self,kv_str:str):
        result = {}
        items = kv_str.strip().split(';')
        for item in items:
            try:
                key, value = item.strip().split('=')
                result[key.strip()] = value.strip()
            except Exception as e:
                # print(f"解析字符串为字典错误: {e}")
                pass
        return result
    def add_cookies(self,cookies):
        for cookie in cookies:
            self.driver.add_cookie(cookie)
        pass    
    def add_cookie(self,cookie):
        self.driver.add_cookie(cookie)
        pass    
    def _download_file(self, url, save_path):
        """下载文件并显示进度"""
        import requests
        from tqdm import tqdm
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        
        with open(save_path, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=save_path) as pbar:
                for data in response.iter_content(block_size):
                    f.write(data)
                    pbar.update(len(data))
    
    def _get_latest_firefox_url(self):
        """获取最新版Firefox下载链接"""
        import requests
        try:
            # 使用 Mozilla 的 API 获取最新版本信息
            response = requests.get("https://product-details.mozilla.org/1.0/firefox_versions.json")
            response.raise_for_status()
            versions = response.json()
            latest_version = versions["LATEST_FIREFOX_VERSION"]
            
            # 构建下载链接（适用于 Windows 64 位中文版）
            return f"https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=zh-CN"
        except Exception as e:
            print(f"获取最新 Firefox 下载链接失败: {e}")
            # 提供一个备用链接以防 API 不可用
            return "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=zh-CN"
    def _install_firefox_windows(self):
        """Windows平台安装Firefox"""
        import tempfile
        import os
        
        print("正在下载Firefox安装包...")
        download_url = self._get_latest_firefox_url()
        temp_dir = tempfile.gettempdir()
        installer_path = os.path.join(temp_dir, "firefox_installer.exe")
        
        try:
            self._download_file(download_url, installer_path)
            print("正在安装Firefox...")
            subprocess.run([installer_path, "/S"], check=True)
            print("Firefox安装完成")
        finally:
            if os.path.exists(installer_path):
                os.remove(installer_path)
    
    def _install_firefox(self):
        """自动安装Firefox浏览器"""
        try:
            if self.system == "windows":
                # Windows安装逻辑
                if not self._is_firefox_installed_windows():
                    self._install_firefox_windows()
            elif self.system == "linux":
                # Linux安装逻辑
                if not self._is_firefox_installed_linux():
                    print("正在通过包管理器安装Firefox...")
                    subprocess.run([ "apt-get", "install","--no-install-recommends","-f" ,"-y", "firefox"], check=True)
            elif self.system == "darwin":
                # macOS安装逻辑
                if not self._is_firefox_installed_mac():
                    print("请手动安装Firefox浏览器：")
                    print("1. 访问 https://www.mozilla.org/firefox/new/")
                    print("2. 下载并安装Firefox")
                    print("3. 将Firefox.app移动到Applications文件夹")
                    raise Exception("macOS系统需要手动安装Firefox")
        except Exception as e:
            print(f"Firefox安装失败: {str(e)}")
            raise

    def _is_firefox_installed_windows(self):
        """检查Windows是否已安装Firefox"""
        common_paths = [
            os.path.expandvars("%PROGRAMFILES%\\Mozilla Firefox\\firefox.exe"),
            os.path.expandvars("%PROGRAMFILES(x86)%\\Mozilla Firefox\\firefox.exe")
        ]
        return any(os.path.exists(path) for path in common_paths)

    def _is_firefox_installed_linux(self):
        """检查Linux是否已安装Firefox"""
        try:
            subprocess.run(["which", "firefox"], check=True, stdout=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False

    def _is_firefox_installed_mac(self):
        """检查macOS是否已安装Firefox"""
        common_paths = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            os.path.expanduser("~/Applications/Firefox.app/Contents/MacOS/firefox")
        ]
        return any(os.path.exists(path) for path in common_paths)

    def _validate_existing_driver(self, path):
        """验证现有驱动是否可用"""
        if not os.path.exists(path):
            return False
            
        # Windows系统验证
        if self.system == "windows":
            # 确保路径以.exe结尾且可读
            if not path.lower().endswith('.exe'):
                # 尝试添加.exe后缀
                new_path = path + '.exe'
                if os.path.exists(new_path):
                    return True
                return False
            if not os.access(path, os.R_OK):
                return False
                
        # Linux/Mac系统验证
        if self.system in ("linux", "darwin"):
            if not os.access(path, os.X_OK):
                try:
                    os.chmod(path, 0o755)
                except:
                    return False
                    
        return True
    def get_driver_path(self):
        """根据操作系统返回正确的driver路径"""
        if self.system == "windows":
            driver_name = "geckodriver.exe"
        elif self.system == "darwin":
            # macOS系统添加架构后缀
            arch_suffix = "_arm64" if platform.machine() == "arm64" else "_intel"
            driver_name = f"geckodriver{arch_suffix}"
        else:
            driver_name = "geckodriver"
        return os.path.join(os.path.dirname(__file__), "driver", driver_name)
    def _setup_driver(self):
        """自动配置geckodriver"""
        # 优先检查本地驱动
        local_driver = self.get_driver_path()
        if self._validate_existing_driver(local_driver):
            self.driver_path = local_driver
            print("使用本地驱动:", local_driver)
            return
            
        # 本地驱动不可用则尝试自动下载
        try:
            # 使用阿里云镜像源配置
            os.environ['WDM_SSL_VERIFY'] = '0'
            os.environ['WDM_LOCAL'] = '1'
            
            # 尝试从华为云镜像直接下载
            try:
                import requests
                import re
                import tarfile
                import zipfile
                
                # 获取最新版本
                response = requests.get("https://repo.huaweicloud.com/geckodriver/")
                response.raise_for_status()
                
                # 解析最新版本号
                versions = re.findall(r'href="v(\d+\.\d+\.\d+)/"', response.text)
                if not versions:
                    raise Exception("无法从华为云镜像获取geckodriver版本")
                latest_version = sorted(versions, key=lambda v: [int(n) for n in v.split('.')])[-1]
                # 最新版本
                print(f"最新版本: {latest_version}")
                # 确定平台和文件后缀
                if self.system == "windows":
                    platform_name = "win64"
                    ext = "zip"
                elif self.system == "linux":
                    platform_name = "linux64"
                    ext = "tar.gz"
                elif self.system == "darwin":
                    platform_name = "macos-aarch64" if platform.machine() == "arm64" else "macos"
                    ext = "tar.gz"
                else:
                    raise Exception(f"不支持的系统: {self.system}")
                
                # 构建下载URL
                download_url = f"https://repo.huaweicloud.com/geckodriver/v{latest_version}/geckodriver-v{latest_version}-{platform_name}.{ext}"
                
                # 下载文件
                driver_dir = os.path.join(os.path.dirname(__file__), "driver")
                os.makedirs(driver_dir, exist_ok=True)
                archive_path = os.path.join(driver_dir, f"geckodriver.{ext}")
                self._download_file(download_url, archive_path)
                
                # 解压文件
                if self.system == "windows":
                    extract_path = os.path.join(driver_dir, "geckodriver.exe")
                    with zipfile.ZipFile(archive_path) as zip_ref:
                        zip_ref.extract("geckodriver.exe", path=driver_dir)
                elif self.system == "darwin":
                    # 为macOS添加架构后缀
                    arch_suffix = "_arm64" if platform.machine() == "arm64" else "_intel"
                    extract_path = os.path.join(driver_dir, f"geckodriver{arch_suffix}")
                    with tarfile.open(archive_path, "r:gz") as tar:
                        # 先提取到临时路径，然后重命名
                        tar.extract("geckodriver", path=driver_dir)
                        temp_path = os.path.join(driver_dir, "geckodriver")
                        if os.path.exists(extract_path):
                            os.remove(extract_path)
                        os.rename(temp_path, extract_path)
                    os.chmod(extract_path, 0o755)
                else:
                    extract_path = os.path.join(driver_dir, "geckodriver")
                    with tarfile.open(archive_path, "r:gz") as tar:
                        tar.extract("geckodriver", path=driver_dir)
                    os.chmod(extract_path, 0o755)
                
                # 清理临时文件
                os.remove(archive_path)
                self.driver_path = extract_path
                
            except Exception as mirror_error:
                print("华为云镜像直接下载失败，尝试webdriver_manager...", mirror_error)
                try:
                    self.driver_path = GeckoDriverManager().install()
                except Exception as official_error:
                    print("驱动自动安装失败，请手动下载:")
                    print("1. 访问 https://github.com/mozilla/geckodriver/releases")
                    print("2. 下载对应系统的版本")
                    print("3. 解压后将geckodriver放入driver/driver目录")
                    raise official_error
            
            # 设置浏览器路径
            if self.system == "windows":
                self.browser_path = next(
                    (p for p in [
                        os.path.expandvars("%PROGRAMFILES%\\Mozilla Firefox\\firefox.exe"),
                        os.path.expandvars("%PROGRAMFILES(x86)%\\Mozilla Firefox\\firefox.exe")
                    ] if os.path.exists(p)), None)
            elif self.system == "linux":
                self.browser_path = "/usr/bin/firefox"
            elif self.system == "darwin":
                # macOS Firefox路径
                possible_paths = [
                    "/Applications/Firefox.app/Contents/MacOS/firefox",
                    os.path.expanduser("~/Applications/Firefox.app/Contents/MacOS/firefox")
                ]
                self.browser_path = next((p for p in possible_paths if os.path.exists(p)), None)
            
            if not self.browser_path:
                raise Exception("无法找到Firefox浏览器路径")
                
            self.options.binary_location = self.browser_path
        except Exception as e:
            print(f"驱动配置失败: {str(e)}")
            raise

    def start_browser(self, headless=True):
        """启动浏览器"""
        try:
            self._install_firefox()
            self._setup_driver()
            self.options.page_load_strategy = "eager"
          
            # 禁用浏览器错误输出
            self.options.set_preference("webdriver.log.driver", "OFF")
            self.options.set_preference("webdriver.log.browser", "OFF")
            from core.config import cfg
            if headless and cfg.get("debug",False)==False:
                self.options.add_argument("--headless")          # 启用无界面模式
                pass  
            if headless and  self.system != "windows":
                self.options.add_argument("--headless")          # 启用无界面模式
                self.options.add_argument("--disable-gpu")       # 禁用 GPU 加速
                self.options.add_argument("--no-sandbox")        # 无沙盒模式（Linux 必需）
                self.options.add_argument("--disable-dev-shm-usage")  # 解决 Linux 内存不足问题
            # 隐藏状态栏和任务栏
            self.options.set_preference("toolkit.legacyUserProfileCustomizations.stylesheets", True)  # 允许自定义样式

            service = Service(executable_path=self.driver_path)
            self.driver = webdriver.Firefox(service=service, options=self.options)
            # self.driver.set_window_size(100, 100)
            # if self.system == "windows":
            #     self.driver.set_window_position(-1000, 1000)
            return self.driver
        except WebDriverException as e:
            print(f"浏览器启动失败: {str(e)}")
            print(e)
            raise
    def __del__(self):
        """确保浏览器关闭"""
        self.Close()
    def open_url(self, url):
        """打开指定URL"""
        try:
            self.driver.get(url)
        except WebDriverException as e:
            # print(f"打开URL失败: {str(e)}")
            # print(e)
            raise Exception(f"打开URL失败: {str(e)}")
        except Exception as e:
            # print(f"打开URL失败: {str(e)}")
            raise Exception(f"打开URL失败: {str(e)}")

    def Close(self):
        """关闭浏览器"""
        self.HasLogin= False
        if hasattr(self, 'driver'):
            self.driver.quit()
            self.isClose=True

    def dict_to_json(self, data_dict):
        """
        将字典转换为JSON字符串
        :param data_dict: 需要转换的字典
        :return: JSON字符串或空字符串（转换失败时）
        """
        try:
            return json.dumps(data_dict, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as e:
            print(f"字典转JSON失败: {e}")
            return ""

# 示例用法
# if __name__ == "__main__":
#     controller = FirefoxController()
#     try:
#         controller.start_browser()
#         controller.open_url("https://mp.weixin.qq.com/")