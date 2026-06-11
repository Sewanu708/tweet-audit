from sqlmodel import  Session, create_engine, SQLModel, Field
from sqlalchemy.dialects.postgresql import JSON
from typing import Any
from settings import env

engine = create_engine(env['database_url'])



class Idemptency(SQLModel, table=True):
    response: dict[str,Any] = Field(default={}, sa_type=JSON)
    tweet_id:str = Field(primary_key=True)

SQLModel.metadata.create_all(engine)