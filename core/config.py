import yaml
import sys
import os
import argparse
from string import Template
class Config: 
    config_path=None
    config={}
    def __init__(self,config_path=None):
        self.args=self.parse_args()
        self.config_path = config_path or self.args.config
        self.get_config()
    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-config', help='配置文件', default='config.yaml')
        parser.add_argument('-job', help='启动任务', default=False)
        parser.add_argument('-init', help='初始化数据库,初始化用户', default=False)
        args, _ = parser.parse_known_args()
        return args
    def save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f)
        self.reload()
    def replace_env_vars(self,data):
            if isinstance(data, dict):
                return {k: self.replace_env_vars(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [self.replace_env_vars(item) for item in data]
            elif isinstance(data, str):
                try:
                    import re
                    # 匹配 ${VAR:-default} 或 ${VAR} 格式
                    pattern = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')
                    def replace_match(match):
                        var_name = match.group(1)
                        default_value = match.group(2)
                        return os.getenv(var_name, default_value) if default_value is not None else os.getenv(var_name, '')
                    return pattern.sub(replace_match, data)
                except:
                    return data
            return data
    def get_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.config = config
                self._config = self.replace_env_vars(config)
                return self.config
        except Exception as e:
            print(f"Error loading configuration file {self.config_path}: {e}")
            sys.exit(1)
    def reload(self):
        self.config=self.get_config()
    def set(self,key,default:any=None):
        self.config[key] = default
        self.save_config()
    def __fix(self,v:str):
        if v in ("", "''", '""', None):
            return ""
        try:
            # 尝试转换为布尔值
            if v.lower() in ('true', 'false'):
                return v.lower() == 'true'
            # 尝试转换为整数
            if v.isdigit():
                return int(v)
            # 尝试转换为浮点数
            if '.' in v and all(part.isdigit() for part in v.split('.') if part):
                return float(v)
            return v
        except:
            return v
    def get(self,key,default:any=None):
        _config=self.replace_env_vars(self.config)
        
        # 支持嵌套key访问
        keys = key.split('.') if isinstance(key, str) else [key]
        value = _config
        try:
            for k in keys:
                value = value[k]
            val=self.__fix(value)
            if val is None and default is not None:
                return default
            else:
                return val
        except (KeyError, TypeError):
            print("Key {} not found in configuration".format(key))
            if default is not None:
                return default
        return None

cfg=Config()
def set_config(key:str,value:str):
    cfg.set(key,value)
def save_config():
    cfg.save_config()
    
DEBUG=cfg.get("debug",False)
APP_NAME=cfg.get("app_name","we-mp-rss")
from core.ver import VERSION,API_BASE
print(f"版本:{VERSION} API_BASE:{API_BASE}")