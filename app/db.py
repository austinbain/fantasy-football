from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


def make_engine(db_path: str):
    if db_path == ":memory:":
        url = "sqlite:///:memory:"
        # StaticPool shares a single connection across threads so the
        # in-memory database survives across sessions/threads (e.g. when
        # served by FastAPI's threaded request handling in tests).
        engine = create_engine(url, connect_args={"check_same_thread": False},
                                poolclass=StaticPool)
    else:
        url = f"sqlite:///{db_path}"
        engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
