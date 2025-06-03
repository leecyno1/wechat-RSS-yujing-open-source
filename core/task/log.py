from logging.handlers import RotatingFileHandler
import logging
global logger
# 创建logger对象
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 设置最低日志级别
# 创建文件处理器，每天一个文件，保留7天备份
handler = RotatingFileHandler('job.log', maxBytes=1024*1024, backupCount=7)
handler.setLevel(logging.DEBUG)
# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
# 创建格式器并添加到处理器
formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
# 将处理器添加到logger
logger.addHandler(handler)
logger.addHandler(console_handler)