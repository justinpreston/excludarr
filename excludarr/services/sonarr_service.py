from typing import Callable, Dict, List, Optional

from loguru import logger

import excludarr.utils.output as output
from excludarr.core.sonarr_actions import SonarrActions
from excludarr.utils.config import Config
from excludarr.utils.enums import Action


class SonarrService:
    """Service layer that wraps :class:`SonarrActions`.

    This class centralises all business logic for Sonarr related commands.
    The public methods return data structures instead of printing so that the
    caller (usually the CLI layer) is in control of the output.
    """

    def __init__(self, config: Config, locale: Optional[str] = None):
        self.config = config
        locale = locale or config.locale
        self.actions = SonarrActions(config.sonarr_url, config.sonarr_api_key, locale)

    # ------------------------------------------------------------------
    def _confirm(self, action: Action | str, kind: str, yes: bool) -> bool:
        if yes:
            return True
        return output.ask_confirmation(action, kind)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_series_to_exclude(
        self,
        providers: Optional[List[str]],
        action: Action,
        delete_files: bool,
        disable_progress: bool,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[int, dict]:
        if not providers:
            providers = self.config.providers

        series = self.actions.get_series_to_exclude(
            providers,
            self.config.fast_search,
            disable_progress,
            tmdb_api_key=self.config.tmdb_api_key,
            progress_cb=progress_cb,
        )

        for _, values in series.items():
            if delete_files:
                values["episodes"] = [
                    ep
                    for ep in values["episodes"]
                    if ep.get("monitored", False) or ep.get("has_file", False)
                ]
                values["seasons"] = [
                    se
                    for se in values["seasons"]
                    if se.get("monitored", False) or se.get("has_file", False)
                ]
            else:
                values["episodes"] = [
                    ep for ep in values["episodes"] if ep.get("monitored", False)
                ]
                values["seasons"] = [
                    se for se in values["seasons"] if se.get("monitored", False)
                ]

            sonarr_total_monitored_seasons = len(
                [s for s in values["sonarr_object"]["seasons"] if s.get("monitored", False)]
            )
            total_seasons = len([s["season"] for s in values["seasons"]])

            if (
                total_seasons == sonarr_total_monitored_seasons
                and values["ended"]
                and action == Action.delete
            ):
                values["full_delete"] = True
            else:
                values["full_delete"] = False

        if action == Action.not_monitored:
            series = {
                id: val
                for id, val in series.items()
                if (val["episodes"] or val["seasons"])
                and val["title"] not in self.config.sonarr_excludes
            }
        else:
            series = {
                id: val
                for id, val in series.items()
                if ((val["episodes"] or val["seasons"]) or val["full_delete"]) and val["title"] not in self.config.sonarr_excludes
            }

        return series

    def get_series_to_re_add(
        self,
        providers: Optional[List[str]],
        disable_progress: bool,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[int, dict]:
        if not providers:
            providers = self.config.providers

        series = self.actions.get_series_to_re_add(
            providers,
            self.config.fast_search,
            disable_progress,
            tmdb_api_key=self.config.tmdb_api_key,
            progress_cb=progress_cb,
        )

        for _, values in series.items():
            values["episodes"] = [
                ep for ep in values["episodes"] if not ep.get("monitored", True)
            ]
            values["seasons"] = [
                se for se in values["seasons"] if not se.get("monitored", True)
            ]

        series = {
            id: val
            for id, val in series.items()
            if (
                val["episodes"]
                or val["seasons"]
                or not val["sonarr_object"]["monitored"]
            )
            and val["title"] not in self.config.sonarr_excludes
        }

        return series

    # ------------------------------------------------------------------
    # Business actions
    # ------------------------------------------------------------------
    def exclude_series(
        self,
        series: Dict[int, dict],
        action: Action,
        delete_files: bool,
        exclusion: bool,
        yes: bool,
    ) -> Dict[str, object]:
        if not series:
            return {"excluded": False, "ids": []}

        if not self._confirm(action, "series", yes):
            logger.warning(
                "Aborting Excludarr because user did not confirm the question"
            )
            return {"excluded": False, "ids": []}

        for sonarr_id, data in series.items():
            sonarr_object = data["sonarr_object"]
            sonarr_total_seasons = sonarr_object["statistics"]["seasonCount"]
            sonarr_full_delete = data["full_delete"]
            seasons = [s["season"] for s in data["seasons"]]
            episodes = data["episodes"]
            episode_ids = [
                ep["episode_id"]
                for ep in episodes
                if ep.get("episode_id", False)
            ]
            episode_files = data["sonarr_file_ids"]

            if sonarr_full_delete:
                if action == Action.delete:
                    self.actions.delete_serie(sonarr_id, delete_files, exclusion)
                elif action == Action.not_monitored:
                    self.actions.disable_monitored_serie(sonarr_id, sonarr_object)
                    self.actions.disable_monitored_seasons(
                        sonarr_id, sonarr_object, list(range(sonarr_total_seasons + 1))
                    )
                    if delete_files and episode_files:
                        self.actions.delete_episode_files(sonarr_id, episode_files)
            else:
                if seasons:
                    self.actions.disable_monitored_seasons(
                        sonarr_id, sonarr_object, seasons
                    )
                if episodes:
                    self.actions.disable_monitored_episodes(sonarr_id, episode_ids)
                if delete_files and episode_files:
                    self.actions.delete_episode_files(sonarr_id, episode_files)

        return {"excluded": True, "ids": list(series.keys())}

    def readd_series(self, series: Dict[int, dict], yes: bool) -> Dict[str, object]:
        if not series:
            return {"re_added": False, "ids": []}

        if not self._confirm("re-add", "series", yes):
            logger.warning(
                "Aborting Excludarr because user did not confirm the question"
            )
            return {"re_added": False, "ids": []}

        for sonarr_id, data in series.items():
            sonarr_object = data["sonarr_object"]
            sonarr_total_seasons = sonarr_object["statistics"]["seasonCount"]
            sonarr_total_not_monitored_seasons = len(
                [s for s in sonarr_object["seasons"] if not s["monitored"]]
            )
            seasons = [s["season"] for s in data["seasons"]]
            total_seasons = len(seasons)
            episodes = data["episodes"]
            episode_ids = [
                ep["episode_id"] for ep in episodes if ep.get("episode_id", False)
            ]
            all_episode_ids = data.get("all_episode_ids", [])

            if (
                sonarr_total_not_monitored_seasons == total_seasons
                and sonarr_total_not_monitored_seasons != 0
            ):
                self.actions.enable_monitored_serie(sonarr_id, sonarr_object)
                self.actions.enable_monitored_seasons(
                    sonarr_id, sonarr_object, list(range(sonarr_total_seasons + 1))
                )
                self.actions.enable_monitored_episodes(sonarr_id, all_episode_ids)
            else:
                self.actions.enable_monitored_serie(sonarr_id, sonarr_object)
                if seasons:
                    self.actions.enable_monitored_seasons(
                        sonarr_id, sonarr_object, seasons
                    )
                if episodes:
                    self.actions.enable_monitored_episodes(sonarr_id, episode_ids)

        return {"re_added": True, "ids": list(series.keys())}
