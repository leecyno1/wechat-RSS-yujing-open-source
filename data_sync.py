import os
import importlib
from typing import Dict, Type
from sqlalchemy import create_engine, MetaData, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging

class DatabaseSynchronizer:
    """数据库模型同步器"""
    
    def __init__(self, db_url: str, models_dir: str = "core/models"):
        """
        初始化同步器
        
        :param db_url: 数据库连接URL
        :param models_dir: 模型目录路径
        """
        self.db_url = db_url
        self.models_dir = models_dir
        self.engine = None
        self.models = {}
        
        # 配置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("Sync")
    
    def load_models(self) -> Dict[str, Type[declarative_base()]]:
        """动态加载所有模型类"""
        self.models = {}
        for filename in os.listdir(self.models_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(f"core.models.{module_name}")
                    for name, obj in module.__dict__.items():
                        if isinstance(obj, type) and hasattr(obj, "__tablename__"):
                            self.models[obj.__tablename__] = obj
                    self.logger.info(f"成功加载模型模块: {module_name}")
                except ImportError as e:
                    self.logger.warning(f"无法加载模型模块 {module_name}: {e}")
        return self.models
    
    def _map_types_for_sqlite(self, model):
        """为SQLite处理特殊类型映射"""
        if "sqlite" not in self.db_url:
            return
            
        for column in model.__table__.columns:
            if hasattr(column.type, "__visit_name__"):
                if column.type.__visit_name__ == "MEDIUMTEXT":
                    from sqlalchemy import Text
                    column.type = Text()
    
    def sync(self):
        """同步模型到数据库"""
        try:
            self.engine = create_engine(self.db_url)
            metadata = MetaData()
            
            # 反射现有数据库结构
            metadata.reflect(bind=self.engine)
            
            # 处理SQLite的特殊类型映射
            if "sqlite" in self.db_url:
                for model in self.models.values():
                    self._map_types_for_sqlite(model)
            
            # 加载模型
            if not self.models:
                self.load_models()
                if not self.models:
                    self.logger.error("没有找到任何模型类")
                    return
            
            # 为不同数据库类型处理自增主键
            if "sqlite" in self.db_url:
                # SQLite使用AUTOINCREMENT
                pass  # SQLAlchemy默认处理
            elif "mysql" in self.db_url:
                # MySQL使用AUTO_INCREMENT
                pass  # SQLAlchemy默认处理
            
            # 创建所有表（如果不存在）
            for model in self.models.values():
                if not inspect(self.engine).has_table(model.__tablename__):
                    model.metadata.create_all(self.engine)
                    self.logger.info(f"创建表: {model.__tablename__}")
                else:
                    self.logger.info(f"表已存在: {model.__tablename__}")
                    
            self.logger.info("模型同步完成")
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"数据库同步失败: {e}")
            # raise

def main():
    # 示例使用
    synchronizer = DatabaseSynchronizer(db_url="sqlite:///data/db.db")
    synchronizer.sync()

if __name__ == "__main__":
    main()