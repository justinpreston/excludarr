import asyncio
import uuid
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, WebSocket
from pydantic import BaseModel

from excludarr.services.radarr_service import RadarrService
from excludarr.services.sonarr_service import SonarrService
from excludarr.utils.config import Config
from excludarr.utils.enums import Action
from excludarr.modules.justwatch.justwatch import JustWatch


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
        task_manager.update(
            task_id, status="failed", progress=1.0, result={"error": str(exc)}
        )


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
        task_manager.update(
            task_id, status="failed", progress=1.0, result={"error": str(exc)}
        )


@radarr_router.post("/exclude", response_model=TaskInfo)
async def radarr_exclude(
    payload: RadarrExcludeRequest, background_tasks: BackgroundTasks
) -> TaskInfo:
    task_id = task_manager.create()
    background_tasks.add_task(run_radarr_exclude, task_id, payload)
    return TaskInfo(task_id=task_id)


@radarr_router.post("/re-add", response_model=TaskInfo)
async def radarr_re_add(
    payload: RadarrReAddRequest, background_tasks: BackgroundTasks
) -> TaskInfo:
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
        task_manager.update(
            task_id, status="failed", progress=1.0, result={"error": str(exc)}
        )


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
        task_manager.update(
            task_id, status="failed", progress=1.0, result={"error": str(exc)}
        )


@sonarr_router.post("/exclude", response_model=TaskInfo)
async def sonarr_exclude(
    payload: SonarrExcludeRequest, background_tasks: BackgroundTasks
) -> TaskInfo:
    task_id = task_manager.create()
    background_tasks.add_task(run_sonarr_exclude, task_id, payload)
    return TaskInfo(task_id=task_id)


@sonarr_router.post("/re-add", response_model=TaskInfo)
async def sonarr_re_add(
    payload: SonarrReAddRequest, background_tasks: BackgroundTasks
) -> TaskInfo:
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
