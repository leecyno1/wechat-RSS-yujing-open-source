import queue
import threading
from typing import Callable, Any, Optional

class TaskQueueManager:
    """任务队列管理器，用于管理和执行排队任务"""
    
    def __init__(self):
        """初始化任务队列"""
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._is_running = False
        
    def add_task(self, task: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """添加任务到队列
        
        Args:
            task: 要执行的任务函数
            *args: 任务函数的参数
            **kwargs: 任务函数的关键字参数
        """
        with self._lock:
            self._queue.put((task, args, kwargs))
        # print(f"任务添加成功")
    def run_task_background(self)->None:
        threading.Thread(target=self.run_tasks, daemon=True).start()  
        print("任务队列后台运行")
    def run_tasks(self) -> None:
        """执行队列中的所有任务，并持续运行以接收新任务"""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            
        try:
            while self._is_running:
                with self._lock:
                    if self._queue.empty():
                        continue
                    task, args, kwargs = self._queue.get()
                
                try:
                    task(*args, **kwargs)
                except Exception as e:
                    print(f"任务执行失败: {e}")
                finally:
                    self._queue.task_done()
        finally:
            with self._lock:
                self._is_running = False
    
    def stop(self) -> None:
        """停止任务执行"""
        with self._lock:
            self._is_running = False
    
    def get_queue_info(self) -> dict:
        """
        获取队列的当前状态信息
        
        返回:
            dict: 包含队列信息的字典，包括:
                - is_running: 队列是否正在运行
                - pending_tasks: 等待执行的任务数量
        """
        with self._lock:
            return {
                'is_running': self._is_running,
                'pending_tasks': self._queue.qsize()
            }
TaskQueue = TaskQueueManager()
TaskQueue.run_task_background()
if __name__ == "__main__":
    def task1():
        print("执行任务1")

    def task2(name):
        print(f"执行任务2，参数: {name}")

    manager = TaskQueueManager()
    manager.add_task(task1)
    manager.add_task(task2, "测试任务")
    manager.run_tasks()  # 按顺序执行任务1和任务2