from driver.base import WX_API
import os
from core.task import TaskScheduler
from driver.success import Success
def auth():
    WX_API.Token(callback=Success)
if os.getenv('WE_RSS.AUTH',False):
    auth_task=TaskScheduler()
    if os.getenv('DEBUG',True):
        auth_task.add_cron_job(auth, "*/1 * * * *",tag="授权定时更新")
    else:
        auth_task.add_cron_job(auth, "0 */1 * * *",tag="授权定时更新")
    auth_task.start()