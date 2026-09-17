from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base


def make_engine(db_path: str):
    url = "sqlite:///:memory:" if db_path == ":memory:" else f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
