#!/usr/bin/env python3
"""
简化的浏览器资源测试
"""

import os
import sys
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_imports():
    """测试基本导入"""
    print("测试 1: 基本导入")
    try:
        from driver.wxarticle import get_web_fetcher, _fetcher_manager
        from driver.playwright_driver import get_control_driver, _controller_manager
        print("✅ 导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_singleton_pattern():
    """测试单例模式"""
    print("\n测试 2: 单例模式")
    try:
        from driver.wxarticle import get_web_fetcher
        
        fetcher1 = get_web_fetcher()
        fetcher2 = get_web_fetcher()
        
        if fetcher1 is fetcher2:
            print("✅ 单例模式工作正常")
            return True
        else:
            print("❌ 单例模式失败")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_resource_cleanup():
    """测试资源清理"""
    print("\n测试 3: 资源清理")
    try:
        from driver.wxarticle import WXArticleFetcher
        
        print("创建实例...")
        fetcher = WXArticleFetcher()
        
        print("尝试清理...")
        fetcher.Close()
        
        print("✅ 资源清理正常")
        return True
    except Exception as e:
        print(f"❌ 资源清理失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("浏览器资源修复简化测试")
    print("=" * 50)
    
    results = []
    
    results.append(test_basic_imports())
    results.append(test_singleton_pattern()) 
    results.append(test_resource_cleanup())
    
    print("\n" + "=" * 50)
    print("测试结果:")
    
    passed = sum(results)
    total = len(results)
    
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("🎉 所有基础测试通过！")
        return True
    else:
        print("❌ 部分测试失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)