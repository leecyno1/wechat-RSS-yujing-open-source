from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from typing import Optional, List
from .models import Feed, Article
from .config import cfg
from core.models.base import Base  
# 声明基类
# Base = declarative_base()

class Db:
    def __init__(self):
        self.session: Optional[sessionmaker] = None
        self.engine = None
        
    def init(self, con_str: str) -> None:
        """Initialize database connection and create tables"""
        try:
            self.engine = create_engine(con_str)
            Session = sessionmaker(bind=self.engine)
            self.session = Session()
        except Exception as e:
            print(f"Error creating database connection: {e}")
            raise
    def create_tables(self):
        """Create all tables defined in models"""
        from core.models.base import Base as B # 导入所有模型
        Base.metadata.create_all(self.engine)
        print('All Tables Created Successfully!')    
        
    def close(self) -> None:
        """Close the database connection"""
        if self.session:
            self.session.close()
            
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
            
    def add_article(self, article_data: dict) -> bool:
        try:
            from datetime import datetime
            art = Article(**article_data)
            if art.created_at is None:
                art.created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if art.updated_at is None:
                art.updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            art.created_at=datetime.strptime(art.created_at ,'%Y-%m-%d %H:%M:%S')
            art.updated_at=datetime.strptime(art.updated_at,'%Y-%m-%d %H:%M:%S')
            from core.models.base import DATA_STATUS
            art.status=DATA_STATUS.ACTIVE
            self.session.add(art) 
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            print(f"Failed to add article: {e}",e)
            return False
        return True    
        
    def get_articles(self, id:str=None, limit:int=30, offset:int=0) -> List[Article]:
        try:
            data = self.session.query(Article).limit(limit).offset(offset)
            return data
        except Exception as e:
            print(f"Failed to fetch Feed: {e}")
            return e    
             
    def get_all_mps(self) -> List[Feed]:
        """Get all Feed records"""
        try:
            return self.session.query(Feed).all()
        except Exception as e:
            print(f"Failed to fetch Feed: {e}")
            return e
            
    def get_mps_list(self, mp_ids:str) -> List[Feed]:
        try:
            ids=mp_ids.split(',')
            data = self.session.query(Feed).filter(Feed.id.in_(ids)).all()
            return data
        except Exception as e:
            print(f"Failed to fetch Feed: {e}")
            return e
    def get_mps(self, mp_id:str) -> Optional[Feed]:
        try:
            ids=mp_id.split(',')
            data = self.session.query(Feed).filter_by(id= mp_id).first()
            return data
        except Exception as e:
            print(f"Failed to fetch Feed: {e}")
            return e

    def get_faker_id(self, mp_id:str):
        data = self.get_mps(mp_id)
        return data.faker_id
        
    def get_session(self):
        """获取数据库会话"""
        if not self.session:
            raise Exception("Database not initialized")
        return self.session

# 全局数据库实例
DB = Db()
DB.init(cfg.get("db"))