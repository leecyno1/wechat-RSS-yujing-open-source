from core.db import Db
from core.config import cfg
from core.models import MessageTask
DB = Db()
DB.init(cfg.get("db"))
def get_message_task() -> list[MessageTask]:
    """
    获取单个消息任务详情
    
    参数:
        task_id: 消息任务ID
        
    返回:
        包含消息任务详情的字典，或None如果任务不存在
    """
    try:
        message_task = DB.session.query(MessageTask).filter(MessageTask.status==1).all()
        if not message_task:
            return None
        return message_task
    except Exception as e:
        print(e)
    return None