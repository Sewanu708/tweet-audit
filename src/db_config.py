import sys
from pathlib import Path
from enum import Enum
from sqlmodel import Session, create_engine, SQLModel, Field
from sqlalchemy.dialects.postgresql import JSON
from typing import Any
from datetime import datetime
import uuid

# Add the 'src' directory to Python path
src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from .settings import env

engine = create_engine(env['database_url'])

def get_db():
    with Session(engine) as session:
        yield session



class Idemptency(SQLModel, table=True):
    response: dict[str,Any] = Field(default={}, sa_type=JSON)
    tweet_id:str = Field(primary_key=True)

class Status(str, Enum):
    pending = "pending"
    failed = "failed"
    processing = "processing"
    completed = "completed"

class TweetStatus(str, Enum):
    pending_llm = "pending_llm"
    flagged_filter = "flagged_filter"
    flagged_llm = "flagged_llm"
    skipped = "skipped"
    safe = "safe"
    pending = "pending"

class Jobs(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status:Status = Field(default=Status.pending)
    error:str| None  = None
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    processed_count:int = Field(default=0, nullable=False)
    total:int = Field(default=0, nullable=False)
    flagged_count:int = Field(default=0, nullable=False)


class Tweets (SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tweet_id:str = Field(primary_key=True)
    job_id: uuid.UUID = Field(nullable=False, foreign_key='jobs.id', ondelete='CASCADE')
    is_retweet:bool=False
    content:str 
    flagged:bool=False
    status:TweetStatus = Field(default=TweetStatus.pending)
    reason:str|None = None 
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)






SQLModel.metadata.create_all(engine)