from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Enum as SAEnum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    status = Column(String) # PROCESSING, COMPLETED, FAILED
    result_json = Column(JSON) # Stores the final result structure
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(String, ForeignKey("analyses.id"))
    stage = Column(String)
    message = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
