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
            # 检查多种可能的MEDIUMTEXT表示形式
            type_str = str(column.type).upper()
            if (hasattr(column.type, "__visit_name__") and column.type.__visit_name__ == "MEDIUMTEXT") or \
               "MEDIUMTEXT" in type_str or \
               getattr(column.type, "__class__", None).__name__ == "MEDIUMTEXT":
                from sqlalchemy import Text
                column.type = Text()
                self.logger.debug(f"已将列 {column.name} 的类型从 MEDIUMTEXT 映射为 Text")
    
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
            
            # 创建或更新表结构
            for model in self.models.values():
                table_name = model.__tablename__
                inspector = inspect(self.engine)
                
                if not inspector.has_table(table_name):
                    model.metadata.create_all(self.engine)
                    self.logger.info(f"创建表: {table_name}")
                else:
                    # 检查字段差异并更新表
                    existing_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
                    model_columns = {c.name: c for c in model.__table__.columns}
                    
                    # 检查新增或修改的字段
                    for col_name, model_col in model_columns.items():
                        if col_name not in existing_columns:
                            # 新增字段
                            from sqlalchemy import text
                            with self.engine.begin() as conn:
                                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {model_col.type}"))
                            self.logger.info(f"新增字段: {table_name}.{col_name}")
                    
                    self.logger.info(f"表已同步: {table_name}")
            
            self.logger.info("模型同步完成")
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"数据库同步失败: {e}")
            return False
        finally:
            if self.engine:
                self.engine.dispose()
            # raise

def main():
    # 示例使用
    synchronizer = DatabaseSynchronizer(db_url="sqlite:///data/db.db")
    synchronizer.sync()

if __name__ == "__main__":
    main()