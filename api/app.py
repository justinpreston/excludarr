import asyncio
import os
import uuid
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    status,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from excludarr.services.radarr_service import RadarrService
from excludarr.services.sonarr_service import SonarrService
from excludarr.utils.config import Config
from excludarr.utils.enums import Action
from excludarr.modules.justwatch.justwatch import JustWatch

from . import auth, models, schemas
from .database import SessionLocal, init_db
from cryptography.fernet import Fernet


class RadarrExcludeRequest(BaseModel):
    providers: Optional[List[str]] = None
    action: Action = Action.delete
    delete_files: bool = False
    disable_progress: bool = False
    exclusion: bool = False


class RadarrReAddRequest(BaseModel):
    providers: Optional[List[str]] = None
    disable_progress: bool = False


class SonarrExcludeRequest(BaseModel):
    providers: Optional[List[str]] = None
    action: Action = Action.delete
    delete_files: bool = False
    disable_progress: bool = False
    exclusion: bool = False


class SonarrReAddRequest(BaseModel):
    providers: Optional[List[str]] = None
    disable_progress: bool = False


class ExcludeResponse(BaseModel):
    excluded: bool
    ids: List[int]


class ReAddResponse(BaseModel):
    re_added: bool
    ids: List[int]


class Provider(BaseModel):
    id: int
    short_name: str
    clear_name: str


class TaskInfo(BaseModel):
    task_id: str


class TaskStatus(BaseModel):
    status: str
    progress: float
    result: Optional[Dict[str, Any]] = None


class TaskManager:
    def __init__(self) -> None:
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()

    def create(self) -> str:
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {"status": "pending", "progress": 0.0, "result": None}
        return task_id

    def update(self, task_id: str, **kwargs: Any) -> None:
        with self.lock:
            self.tasks[task_id].update(kwargs)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.tasks.get(task_id)


app = FastAPI()
config = Config()
task_manager = TaskManager()

config_key = os.getenv("CONFIG_SECRET_KEY")
fernet = Fernet(config_key) if config_key else None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = auth.decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    user = db.query(models.User).get(int(user_id))
    if user is None:
        raise credentials_exception
    return user


def encrypt_value(value: Optional[str]) -> Optional[str]:
    if value and fernet:
        return fernet.encrypt(value.encode()).decode()
    return value


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if value and fernet:
        return fernet.decrypt(value.encode()).decode()
    return value


@app.on_event("startup")
def on_startup() -> None:
    init_db()


radarr_router = APIRouter(prefix="/radarr", tags=["radarr"])


def run_radarr_exclude(task_id: str, payload: RadarrExcludeRequest) -> None:
    task_manager.update(task_id, status="running")
    try:
        service = RadarrService(config)

        def progress_cb(current: int, total: int) -> None:
            task_manager.update(task_id, progress=0.9 * current / total)

        movies = service.get_movies_to_exclude(
            payload.providers,
            payload.action,
            payload.disable_progress,
            progress_cb=progress_cb,
        )
        result = service.exclude_movies(
            movies, payload.action, payload.delete_files, payload.exclusion, yes=True
        )
        task_manager.update(task_id, status="completed", progress=1.0, result=result)
    except Exception as exc:  # pragma: no cover - best effort logging
        task_manager.update(task_id, status="failed", progress=1.0, result={"error": str(exc)})


def run_radarr_re_add(task_id: str, payload: RadarrReAddRequest) -> None:
    task_manager.update(task_id, status="running")
    try:
        service = RadarrService(config)

        def progress_cb(current: int, total: int) -> None:
            task_manager.update(task_id, progress=0.9 * current / total)

        movies = service.get_movies_to_re_add(
            payload.providers, payload.disable_progress, progress_cb=progress_cb
        )
        result = service.readd_movies(movies, yes=True)
        task_manager.update(task_id, status="completed", progress=1.0, result=result)
    except Exception as exc:  # pragma: no cover - best effort logging
        task_manager.update(task_id, status="failed", progress=1.0, result={"error": str(exc)})


@radarr_router.post("/exclude", response_model=TaskInfo)
async def radarr_exclude(
    payload: RadarrExcludeRequest, background_tasks: BackgroundTasks
) -> TaskInfo:
    task_id = task_manager.create()
    background_tasks.add_task(run_radarr_exclude, task_id, payload)
    return TaskInfo(task_id=task_id)


@radarr_router.post("/re-add", response_model=TaskInfo)
async def radarr_re_add(payload: RadarrReAddRequest, background_tasks: BackgroundTasks) -> TaskInfo:
    task_id = task_manager.create()
    background_tasks.add_task(run_radarr_re_add, task_id, payload)
    return TaskInfo(task_id=task_id)


sonarr_router = APIRouter(prefix="/sonarr", tags=["sonarr"])


def run_sonarr_exclude(task_id: str, payload: SonarrExcludeRequest) -> None:
    task_manager.update(task_id, status="running")
    try:
        service = SonarrService(config)

        def progress_cb(current: int, total: int) -> None:
            task_manager.update(task_id, progress=0.9 * current / total)

        series = service.get_series_to_exclude(
            payload.providers,
            payload.action,
            payload.delete_files,
            payload.disable_progress,
            progress_cb=progress_cb,
        )
        result = service.exclude_series(
            series, payload.action, payload.delete_files, payload.exclusion, yes=True
        )
        task_manager.update(task_id, status="completed", progress=1.0, result=result)
    except Exception as exc:  # pragma: no cover
        task_manager.update(task_id, status="failed", progress=1.0, result={"error": str(exc)})


def run_sonarr_re_add(task_id: str, payload: SonarrReAddRequest) -> None:
    task_manager.update(task_id, status="running")
    try:
        service = SonarrService(config)

        def progress_cb(current: int, total: int) -> None:
            task_manager.update(task_id, progress=0.9 * current / total)

        series = service.get_series_to_re_add(
            payload.providers, payload.disable_progress, progress_cb=progress_cb
        )
        result = service.readd_series(series, yes=True)
        task_manager.update(task_id, status="completed", progress=1.0, result=result)
    except Exception as exc:  # pragma: no cover
        task_manager.update(task_id, status="failed", progress=1.0, result={"error": str(exc)})


@sonarr_router.post("/exclude", response_model=TaskInfo)
async def sonarr_exclude(
    payload: SonarrExcludeRequest, background_tasks: BackgroundTasks
) -> TaskInfo:
    task_id = task_manager.create()
    background_tasks.add_task(run_sonarr_exclude, task_id, payload)
    return TaskInfo(task_id=task_id)


@sonarr_router.post("/re-add", response_model=TaskInfo)
async def sonarr_re_add(payload: SonarrReAddRequest, background_tasks: BackgroundTasks) -> TaskInfo:
    task_id = task_manager.create()
    background_tasks.add_task(run_sonarr_re_add, task_id, payload)
    return TaskInfo(task_id=task_id)


providers_router = APIRouter(prefix="/providers", tags=["providers"])


@providers_router.get("", response_model=List[Provider])
def list_providers() -> List[Provider]:
    jw = JustWatch(config.locale)
    providers = jw.get_providers()
    return [
        Provider(id=p["id"], short_name=p["short_name"], clear_name=p["clear_name"])
        for p in providers
    ]


@app.post("/auth/register", response_model=schemas.UserRead)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    db_user = models.User(
        username=user.username, password_hash=auth.get_password_hash(user.password)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/auth/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = auth.create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/settings", response_model=schemas.SettingsRead)
def get_settings(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    settings = db.query(models.Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    data = schemas.SettingsRead.from_orm(settings).dict()
    data["radarr_api_key"] = decrypt_value(data.get("radarr_api_key"))
    data["sonarr_api_key"] = decrypt_value(data.get("sonarr_api_key"))
    return data


@app.post("/settings", response_model=schemas.SettingsRead)
def create_settings(
    payload: schemas.SettingsCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.dict(exclude_unset=True)
    if "radarr_api_key" in data:
        data["radarr_api_key"] = encrypt_value(data["radarr_api_key"])
    if "sonarr_api_key" in data:
        data["sonarr_api_key"] = encrypt_value(data["sonarr_api_key"])
    settings = db.query(models.Settings).first()
    if settings:
        for key, value in data.items():
            setattr(settings, key, value)
        db.commit()
        db.refresh(settings)
    else:
        settings = models.Settings(**data)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    result = schemas.SettingsRead.from_orm(settings).dict()
    result["radarr_api_key"] = decrypt_value(result.get("radarr_api_key"))
    result["sonarr_api_key"] = decrypt_value(result.get("sonarr_api_key"))
    return result


@app.delete("/settings", response_model=schemas.SettingsRead)
def delete_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    settings = db.query(models.Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    db.delete(settings)
    db.commit()
    result = schemas.SettingsRead.from_orm(settings).dict()
    result["radarr_api_key"] = decrypt_value(result.get("radarr_api_key"))
    result["sonarr_api_key"] = decrypt_value(result.get("sonarr_api_key"))
    return result


app.include_router(radarr_router)
app.include_router(sonarr_router)
app.include_router(providers_router)


@app.get("/tasks/{task_id}", response_model=TaskStatus)
def get_task(task_id: str) -> TaskStatus:
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(**task)


@app.websocket("/ws/tasks/{task_id}")
async def task_ws(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            task = task_manager.get(task_id)
            if not task:
                await websocket.close()
                break
            await websocket.send_json(task)
            if task["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(1)
    finally:
        await websocket.close()
