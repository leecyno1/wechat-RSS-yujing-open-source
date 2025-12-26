import threading
from driver.base import WX_InterFace
import os
import portalocker
from core.task import TaskScheduler
from driver.success import Success
from core.print import print_warning

def auth():
    # 使用文件锁确保只有一个进程执行
    lock_file = './data/auth_task.lock'
    try:
        with open(lock_file, 'w') as f:
            portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
            def run_auth():
                wx=WX_InterFace()
                # wx.Token(callback=Success)
                wx.switch_account()
            
            thread = threading.Thread(target=run_auth)
            thread.start()
            thread.join()  # 可选：等待完成
    except portalocker.exceptions.LockException:
        # 其他进程直接返回
        pass
if str(os.getenv('WE_RSS.AUTH',False))=="True":
    print_warning("启动授权定时任务")
    auth_task=TaskScheduler()
    auth_task.clear_all_jobs()
    print("是否开启调试模式:",str(os.getenv('DEBUG',False)))
    if str(os.getenv('DEBUG',False))=="True":
        auth_task.add_cron_job(auth, "*/1 * * * *",tag="授权定时更新")
    else:
        auth_task.add_cron_job(auth, "0 */1 * * *",tag="授权定时更新")
    auth_task.start()
