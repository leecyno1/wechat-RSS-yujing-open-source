from driver.wx import WX_API
import os
from core.task import TaskScheduler
from driver.success import Success
def auth():
    WX_API.Token(CallBack=Success)
if os.getenv('WE_RSS.AUTH',False):
    auth_task=TaskScheduler()
    auth_task.add_cron_job(auth, "0 */1 * * *",tag="授权定时更新")
    auth_task.start()