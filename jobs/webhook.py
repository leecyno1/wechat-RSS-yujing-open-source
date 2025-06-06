from core.models.message_task import MessageTask
from core.models.feed import Feed
from core.models.article import Article
from core.notice import notice
from dataclasses import dataclass
from core.lax import TemplateParser
from datetime import datetime
@dataclass
class MessageWebHook:
    task: MessageTask
    feed:Feed
    articles: list[Article]
    pass

def send_message(hook: MessageWebHook) -> str:
    """
    发送格式化消息
    
    参数:
        hook: MessageWebHook对象，包含任务、订阅源和文章信息
        
    返回:
        str: 格式化后的消息内容
    """
    template = hook.task.message_template if hook.task.message_template else """
    订阅源信息:
    # 名称:{{feed.mp_name}}\n
    # 最新文章:\n
    {% if articles %}
    {% for article in articles %}
    - {{ article.title }} ({{ article.pub_date }})\n
    {% endfor %}
    {% else %}
    - 暂无文章\n
    {% endif %}
    """
    parser = TemplateParser(template)
    data = {
        "feed": hook.feed,
        "articles": hook.articles,
        "task": hook.task,
        'now': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    message = parser.render(data)
    # 这里可以添加发送消息的具体实现
    print("发送消息:", message)
    notice(hook.task.web_hook_url, hook.task.name, message)
    return message

def call_webhook(hook: MessageWebHook) -> str:
    """
    调用webhook接口发送数据
    
    参数:
        hook: MessageWebHook对象，包含任务、订阅源和文章信息
        
    返回:
        str: 调用结果信息
        
    异常:
        ValueError: 当webhook调用失败时抛出
    """
    template = hook.task.message_template if hook.task.message_template else """{
        "feed": "{{feed.mp_name}}",
        "articles": [
            {% for article in articles %}
            {"title": "{{article.title}}", "pub_date": "{{article.pub_date}}"}{% if not loop.last %},{% endif %}
            {% endfor %}
        ]
    }"""
    parser = TemplateParser(template)
    data = {
        "feed": hook.feed,
        "articles": hook.articles,
     "task": hook.task,
        'now': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    payload = parser.render(data)
    
    # 检查web_hook_url是否为空
    if not hook.task.web_hook_url:
        raise ValueError("Webhook URL不能为空")
        
    # 发送webhook请求
    import requests
    try:
        response = requests.post(
            hook.task.web_hook_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return "Webhook调用成功"
    except Exception as e:
        raise ValueError(f"Webhook调用失败: {str(e)}")

def web_hook(hook:MessageWebHook):
    """
    根据消息类型路由到对应的处理函数
    
    参数:
        hook: MessageWebHook对象，包含任务、订阅源和文章信息
        
    返回:
        对应处理函数的返回结果
        
    异常:
        ValueError: 当消息类型未知时抛出
    """
    if hook.task.message_type == 0:  # 发送消息
        return send_message(hook)
    elif hook.task.message_type == 1:  # 调用webhook
        return call_webhook(hook)
    else:
        raise ValueError(f"未知的消息类型: {hook.task.message_type}")