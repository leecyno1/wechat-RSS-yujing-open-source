from playwright.sync_api import sync_playwright, TimeoutError

def run():
    playwright=sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)  # 设置 headless=False 可以看到浏览器窗口
    context = browser.new_context()
    page = context.new_page()

    # 导航到初始页面
    initial_url = 'https://mp.weixin.qq.com/'  # 替换为实际的初始URL
    target_substring = 'home'  # 替换为目标URL中的子字符串

    try:
        page.goto(initial_url)
        print(f"导航到初始页面: {initial_url}")

        # 定义一个标志来指示是否已经找到目标URL
        navigation_completed = False

        # # 监听页面导航事件
        def handle_frame_navigated(frame):
            nonlocal navigation_completed
            current_url = frame.url
            if target_substring in current_url and not navigation_completed:
                print(f"页面已成功跳转到包含 '{target_substring}' 的URL: {current_url}")
                navigation_completed = True

        page.on('framenavigated', handle_frame_navigated)


        # 等待页面跳转到包含目标子字符串的URL
        page.wait_for_url(f'**home**',wait_until="domcontentloaded")
        print("继续后续操作...")

    except TimeoutError as e:
        print(f"等待页面跳转超时: {e}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        # 关闭浏览器
        context.close()
        browser.close()

run()


