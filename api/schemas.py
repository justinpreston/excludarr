from typing import List, Optional

from pydantic import BaseModel


class SettingsBase(BaseModel):
    radarr_url: Optional[str] = None
    radarr_api_key: Optional[str] = None
    sonarr_url: Optional[str] = None
    sonarr_api_key: Optional[str] = None
    providers: Optional[List[str]] = None


class SettingsCreate(SettingsBase):
    pass


class SettingsRead(SettingsBase):
    id: int

    class Config:
        orm_mode = True


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int

    class Config:
        orm_mode = True
