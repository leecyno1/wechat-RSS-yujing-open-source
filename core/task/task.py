import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import Callable, Any, Optional
from .log import logger
# 设置日志

class TaskScheduler:
    """
    线程调度器类，支持cron定时任务调度
    使用APScheduler作为底层调度引擎

    Cron表达式说明:
    一个cron表达式有5个或6个空格分隔的时间字段，格式为:
        ┌───────────── 秒 (0 - 59) (6位格式)
        │ ┌───────────── 分钟 (0 - 59)
        │ │ ┌───────────── 小时 (0 - 23)
        │ │ │ ┌───────────── 日 (1 - 31)
        │ │ │ │ ┌───────────── 月 (1 - 12 或 JAN-DEC)
        │ │ │ │ │ ┌───────────── 星期 (0 - 6 或 SUN-SAT，0是周日)
        │ │ │ │ │ │
        * * * * * *
        或
        * * * * * (5位格式)

    特殊字符:
        *   任意值
        ,   值列表分隔符 (如 "MON,WED,FRI")
        -   范围 (如 "9-17" 表示9点到17点)
        /   步长 (如 "0/15" 表示从0开始每15分钟)
        ?   日或星期字段无特定值 (只能用在日或星期字段)

    常用示例:
        "0 0 * * *"     每天午夜执行 (5位)
        "0 9 * * MON"   每周一上午9点执行 (5位)
        "0 */6 * * *"   每6小时执行一次 (5位)
        "0 9-17 * * MON-FRI" 工作日每小时从9点到17点执行 (5位)
        "0 0 1 * *"     每月第一天午夜执行 (5位)
        "0 0 1 1 *"     每年1月1日午夜执行 (5位)
        "30 * * * * *"  每分钟的第30秒执行 (6位)
        "0 0 0 * * *"   每天午夜执行 (6位)
        "0 0 9 * * MON" 每周一上午9点执行 (6位)
    """
    
    def __init__(self):
        """初始化调度器和线程锁"""
        self._scheduler = BackgroundScheduler()
        self._lock = threading.Lock()
        self._jobs = {}
        
    def add_cron_job(self, 
                    func: Callable[..., Any],
                    cron_expr: str,
                    args: Optional[tuple] = None,
                    kwargs: Optional[dict] = None,
                    job_id: Optional[str] = None) -> str:
        """
        添加一个cron定时任务
        
        :param func: 要执行的函数
        :param cron_expr: cron表达式，如"* * * * *"
        :param args: 函数的位置参数
        :param kwargs: 函数的关键字参数
        :param job_id: 任务ID，如果不指定则自动生成
        :return: 任务ID
        """
        with self._lock:
            try:
                logger.info(f"Adding cron job with expression: {cron_expr}")
                
                # 解析cron表达式为各个字段
                fields = cron_expr.split()
                if len(fields) == 5:
                    # 5位格式: 分 时 日 月 周
                    minute, hour, day, month, day_of_week = fields
                    second = "0"  # 默认秒为0
                elif len(fields) == 6:
                    # 6位格式: 秒 分 时 日 月 周
                    second, minute, hour, day, month, day_of_week = fields
                else:
                    error_msg = f"Invalid cron expression: {cron_expr}. Expected 5 or 6 fields."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                trigger = CronTrigger(
                    second=second,
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                )
                
                # 包装任务函数以捕获异常
                def wrapped_func(*args, **kwargs):
                    try:
                        logger.info(f"Executing job {job_id or 'anonymous'}")
                        return func(*args, **kwargs)
                    except Exception as e:
                        logger.error(f"Job {job_id or 'anonymous'} failed: {str(e)}")
                        raise
                
                job = self._scheduler.add_job(
                    wrapped_func,
                    trigger=trigger,
                    args=args,
                    kwargs=kwargs,
                    id=job_id
                )
                self._jobs[job.id] = job
                logger.info(f"Successfully added job {job.id}")
                return job.id
            except Exception as e:
                logger.error(f"Failed to add cron job: {str(e)}")
                raise
    
    def remove_job(self, job_id: str) -> bool:
        """
        移除指定任务
        
        :param job_id: 要移除的任务ID
        :return: 是否成功移除
        """
        with self._lock:
            if job_id in self._jobs:
                self._scheduler.remove_job(job_id)
                del self._jobs[job_id]
                return True
            return False
    
    def start(self) -> None:
        """启动调度器"""
        with self._lock:
            if self._scheduler.running:
                logger.warning("Scheduler is already running")
                return
                
            try:
                logger.info("Starting scheduler...")
                self._scheduler.start()
                logger.info("Scheduler started successfully")
            except Exception as e:
                logger.error(f"Failed to start scheduler: {str(e)}")
                raise
    
    def shutdown(self, wait: bool = True) -> None:
        """
        关闭调度器
        
        :param wait: 是否等待所有任务完成
        """
        with self._lock:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=wait)
                self._jobs.clear()
    
    def get_job_ids(self) -> list[str]:
        """获取所有任务ID"""
        with self._lock:
            return list(self._jobs.keys())
    
    def __enter__(self):
        """支持上下文管理协议"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理协议"""
        self.shutdown()

    def get_scheduler_status(self) -> dict:
        """
        获取调度器状态信息
        
        :return: 包含调度器状态的字典
        """
        with self._lock:
            return {
                'running': self._scheduler.running,
                'job_count': len(self._jobs),
                'next_run_times': [
                    (job_id, job.next_run_time.isoformat() if job.next_run_time else None)
                    for job_id, job in self._jobs.items()
                ]
            }

    def get_job_details(self, job_id: str) -> dict:
        """
        获取任务详细信息
        
        :param job_id: 任务ID
        :return: 包含任务详情的字典
        """
        with self._lock:
            if job_id not in self._jobs:
                raise ValueError(f"Job {job_id} not found")
            
            job = self._jobs[job_id]
            return {
                'id': job.id,
                'name': job.name,
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'last_run_time': job.last_run_time.isoformat() if job.last_run_time else None,
                'last_run_result': job.last_run_result
            }

if __name__ == "__main__":
    # 示例用法
    def sample_task():
        print("定时任务执行中...")
    
    with TaskScheduler() as scheduler:
        # 添加每分钟执行一次的任务
        job_id = scheduler.add_cron_job(sample_task, "* * * * * *")
        print(f"已添加任务: {job_id}")
        input("按Enter键退出...\n")
    pass