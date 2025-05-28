from .wechat import send_wechat_message
from .dingtalk import send_dingtalk_message
from .feishu import send_feishu_message

def notice( webhook_url, title, text,notice_type: str=None):
    """
    公用通知方法，根据类型判断调用哪种通知
    
    参数:
    - notice_type: 通知类型，'wechat' 或 'dingtalk'
    - webhook_url: 对应机器人的Webhook地址
    - title: 消息标题
    - text: 消息内容
    """
    if 'qyapi.weixin.qq.com' in webhook_url:
        notice_type = 'wechat'
    elif 'oapi.dingtalk.com' in webhook_url:
        notice_type = 'dingtalk'
    elif 'open.feishu.cn' in webhook_url:
        notice_type = 'feishu'
    else:
        print('无法根据 webhook_url 识别通知类型')
        return
    
    if notice_type == 'wechat':
        send_wechat_message(webhook_url, title, text)
    elif notice_type == 'dingtalk':
        send_dingtalk_message(webhook_url, title, text)
    elif notice_type == 'feishu':
        send_feishu_message(webhook_url, title, text)
    else:
        print('不支持的通知类型')