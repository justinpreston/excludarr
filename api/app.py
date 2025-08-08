from typing import List, Optional

from fastapi import APIRouter, FastAPI
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


app = FastAPI()
config = Config()

radarr_router = APIRouter(prefix="/radarr", tags=["radarr"])


@radarr_router.post("/exclude", response_model=ExcludeResponse)
def radarr_exclude(payload: RadarrExcludeRequest) -> ExcludeResponse:
    service = RadarrService(config)
    movies = service.get_movies_to_exclude(
        payload.providers, payload.action, payload.disable_progress
    )
    result = service.exclude_movies(
        movies, payload.action, payload.delete_files, payload.exclusion, yes=True
    )
    return ExcludeResponse(**result)


@radarr_router.post("/re-add", response_model=ReAddResponse)
def radarr_re_add(payload: RadarrReAddRequest) -> ReAddResponse:
    service = RadarrService(config)
    movies = service.get_movies_to_re_add(payload.providers, payload.disable_progress)
    result = service.readd_movies(movies, yes=True)
    return ReAddResponse(**result)


sonarr_router = APIRouter(prefix="/sonarr", tags=["sonarr"])


@sonarr_router.post("/exclude", response_model=ExcludeResponse)
def sonarr_exclude(payload: SonarrExcludeRequest) -> ExcludeResponse:
    service = SonarrService(config)
    series = service.get_series_to_exclude(
        payload.providers,
        payload.action,
        payload.delete_files,
        payload.disable_progress,
    )
    result = service.exclude_series(
        series, payload.action, payload.delete_files, payload.exclusion, yes=True
    )
    return ExcludeResponse(**result)


@sonarr_router.post("/re-add", response_model=ReAddResponse)
def sonarr_re_add(payload: SonarrReAddRequest) -> ReAddResponse:
    service = SonarrService(config)
    series = service.get_series_to_re_add(payload.providers, payload.disable_progress)
    result = service.readd_series(series, yes=True)
    return ReAddResponse(**result)


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
