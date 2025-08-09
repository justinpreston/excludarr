from sqlalchemy import Column, Integer, String, JSON

from .database import Base


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    radarr_url = Column(String, nullable=True)
    radarr_api_key = Column(String, nullable=True)
    sonarr_url = Column(String, nullable=True)
    sonarr_api_key = Column(String, nullable=True)
    providers = Column(JSON, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
