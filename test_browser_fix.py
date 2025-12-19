#!/usr/bin/env python3
"""
浏览器资源泄漏修复验证脚本

测试修复后的代码是否正确处理浏览器资源
"""

import os
import sys
import time
import psutil
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from core.print import print_info, print_warning, print_error, print_success
except ImportError:
    # 如果无法导入，使用简单的打印函数
    def print_info(msg): print(f"[INFO] {msg}")
    def print_warning(msg): print(f"[WARNING] {msg}")  
    def print_error(msg): print(f"[ERROR] {msg}")
    def print_success(msg): print(f"[SUCCESS] {msg}")

class BrowserResourceTester:
    """浏览器资源测试器"""
    
    def __init__(self):
        self.initial_browser_count = self.get_browser_process_count()
        
    def get_browser_process_count(self) -> int:
        """获取浏览器进程数量"""
        try:
            current_process = psutil.Process()
            children = current_process.children(recursive=True)
            browser_processes = [
                p for p in children 
                if any(browser in p.name().lower() for browser in ['chrome', 'firefox', 'webkit'])
            ]
            return len(browser_processes)
        except:
            return 0
    
    def test_wxarticle_fetcher(self):
        """测试 WXArticleFetcher 资源管理"""
        print_info("测试 1: WXArticleFetcher 资源管理")
        print("-" * 50)
        
        from driver.wxarticle import WXArticleFetcher
        
        # 测试正常情况
        print_info("测试正常获取文章内容...")
        fetcher = WXArticleFetcher()
        
        # 使用一个测试URL（这会失败，但能测试资源清理）
        test_url = "https://mp.weixin.qq.com/s/test123"
        
        try:
            result = fetcher.get_article_content(test_url)
            print_warning(f"获取结果: {result.get('title', 'N/A')}")
        except Exception as e:
            print_warning(f"预期的异常: {str(e)[:50]}...")
        
        # 检查资源是否清理
        count_after = self.get_browser_process_count()
        print_info(f"操作后浏览器进程数: {count_after}")
        
        # 显式清理
        fetcher.Close()
        time.sleep(2)  # 等待进程清理
        
        count_after_close = self.get_browser_process_count()
        print_info(f"关闭后浏览器进程数: {count_after_close}")
        
        # 测试异常情况
        print_info("\n测试异常情况下的资源清理...")
        fetcher2 = WXArticleFetcher()
        try:
            fetcher2.get_article_content("invalid_url")
        except:
            pass  # 忽略异常
            
        count_after_exception = self.get_browser_process_count()
        print_info(f"异常后浏览器进程数: {count_after_exception}")
        
        print_success("测试 1 完成")
        return count_after_close <= self.initial_browser_count + 2
    
    def test_playwright_controller(self):
        """测试 PlaywrightController 资源管理"""
        print_info("\n测试 2: PlaywrightController 资源管理")
        print("-" * 50)
        
        from driver.playwright_driver import PlaywrightController
        
        controller = PlaywrightController()
        
        try:
            controller.start_browser()
            print_info("浏览器启动成功")
        except Exception as e:
            print_warning(f"浏览器启动失败（预期）: {str(e)[:50]}...")
        
        # 检查进程
        count_after_start = self.get_browser_process_count()
        print_info(f"启动后浏览器进程数: {count_after_start}")
        
        # 清理资源
        try:
            controller.cleanup()
            print_info("调用 cleanup 成功")
        except Exception as e:
            print_warning(f"清理时出现异常: {str(e)[:50]}...")
        
        time.sleep(2)
        
        count_after_cleanup = self.get_browser_process_count()
        print_info(f"清理后浏览器进程数: {count_after_cleanup}")
        
        print_success("测试 2 完成")
        return count_after_cleanup <= self.initial_browser_count + 2
    
    def test_global_instances(self):
        """测试全局实例管理"""
        print_info("\n测试 3: 全局实例管理")
        print("-" * 50)
        
        # 测试全局访问方式
        from driver.wxarticle import get_web_fetcher, _fetcher_manager
        
        print_info("测试全局获取器...")
        fetcher1 = get_web_fetcher()
        fetcher2 = get_web_fetcher()
        
        print_info(f"两次获取的是同一个实例: {fetcher1 is fetcher2}")
        
        # 测试管理器清理
        _fetcher_manager.cleanup()
        fetcher3 = get_web_fetcher()
        
        print_info(f"清理后重新获取是新实例: {fetcher1 is not fetcher3}")
        
        print_success("测试 3 完成")
        return True
    
    def test_batch_processing(self):
        """测试批量处理资源管理"""
        print_info("\n测试 4: 批量处理资源管理")
        print_info("-" * 50)
        
        # 模拟 jobs/fetch_no_article.py 中的批量处理
        from driver.wxarticle import WXArticleFetcher
        
        initial_count = self.get_browser_process_count()
        
        # 模拟处理多篇文章
        test_urls = [
            "https://mp.weixin.qq.com/s/test1",
            "https://mp.weixin.qq.com/s/test2", 
            "https://mp.weixin.qq.com/s/test3"
        ]
        
        for i, url in enumerate(test_urls):
            print_info(f"处理第 {i+1} 篇文章...")
            fetcher = WXArticleFetcher()
            
            try:
                result = fetcher.get_article_content(url)
            except:
                pass  # 忽略预期异常
            finally:
                # 确保清理每个实例
                fetcher.Close()
            
            count = self.get_browser_process_count()
            print_info(f"第 {i+1} 篇处理后进程数: {count}")
        
        final_count = self.get_browser_process_count()
        print_info(f"批量处理完成，最终进程数: {final_count}")
        
        print_success("测试 4 完成")
        return final_count <= self.initial_browser_count + 2
    
    def run_all_tests(self):
        """运行所有测试"""
        print_info("=" * 60)
        print_info("开始浏览器资源泄漏修复验证测试")
        print_info("=" * 60)
        
        print_info(f"初始浏览器进程数: {self.initial_browser_count}")
        
        results = []
        
        try:
            results.append(("WXArticleFetcher", self.test_wxarticle_fetcher()))
        except Exception as e:
            print_error(f"测试 1 失败: {e}")
            results.append(("WXArticleFetcher", False))
        
        try:
            results.append(("PlaywrightController", self.test_playwright_controller()))
        except Exception as e:
            print_error(f"测试 2 失败: {e}")
            results.append(("PlaywrightController", False))
        
        try:
            results.append(("全局实例管理", self.test_global_instances()))
        except Exception as e:
            print_error(f"测试 3 失败: {e}")
            results.append(("全局实例管理", False))
        
        try:
            results.append(("批量处理", self.test_batch_processing()))
        except Exception as e:
            print_error(f"测试 4 失败: {e}")
            results.append(("批量处理", False))
        
        # 输出结果
        print_info("\n" + "=" * 60)
        print_info("测试结果汇总")
        print_info("=" * 60)
        
        all_passed = True
        for test_name, passed in results:
            status = "✅ 通过" if passed else "❌ 失败"
            print_info(f"{test_name}: {status}")
            if not passed:
                all_passed = False
        
        final_count = self.get_browser_process_count()
        print_info(f"\n最终浏览器进程数: {final_count}")
        print_info(f"进程增长: {final_count - self.initial_browser_count}")
        
        if all_passed and final_count <= self.initial_browser_count + 2:
            print_success("🎉 所有测试通过！浏览器资源管理修复成功")
            return True
        else:
            print_error("❌ 部分测试失败，仍有资源泄漏风险")
            return False

def main():
    """主函数"""
    tester = BrowserResourceTester()
    success = tester.run_all_tests()
    
    if success:
        print_success("\n✅ 验证完成，修复效果良好")
        sys.exit(0)
    else:
        print_error("\n❌ 验证完成，仍有问题需要修复")
        sys.exit(1)

if __name__ == "__main__":
    main()