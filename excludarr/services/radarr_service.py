from typing import Dict, List, Optional

from loguru import logger

import excludarr.utils.output as output
from excludarr.core.radarr_actions import RadarrActions
from excludarr.utils.config import Config
from excludarr.utils.enums import Action


class RadarrService:
    """Service layer wrapping :class:`RadarrActions`.

    The service is responsible for moving the business logic that was
    previously implemented inside the CLI commands.  It exposes a couple of
    convenient methods that return structured data so the caller can decide
    how to present the information (for instance in the CLI or in tests).
    """

    def __init__(self, config: Config, locale: Optional[str] = None):
        self.config = config
        locale = locale or config.locale
        self.actions = RadarrActions(config.radarr_url, config.radarr_api_key, locale)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _confirm(self, action: Action | str, kind: str, yes: bool) -> bool:
        """Ask the user for confirmation.

        The function is kept here so that the commands no longer need to know
        about the confirmation routine.  When ``yes`` is True the question is
        skipped.
        """

        if yes:
            return True
        return output.ask_confirmation(action, kind)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_movies_to_exclude(
        self,
        providers: Optional[List[str]],
        action: Action,
        disable_progress: bool,
    ) -> Dict[int, dict]:
        """Return the movies that can be excluded.

        The heavy lifting is done by :class:`RadarrActions`, after which the
        results are filtered based on the configuration and requested action.
        """

        if not providers:
            providers = self.config.providers

        movies = self.actions.get_movies_to_exclude(
        
            providers,
            self.config.fast_search,
            disable_progress,
        )

        if action == Action.not_monitored:
            movies = {
                id: values
                for id, values in movies.items()
                if values["title"] not in self.config.radarr_excludes
                and values["radarr_object"]["monitored"]
            }
        else:
            movies = {
                id: values
                for id, values in movies.items()
                if values["title"] not in self.config.radarr_excludes
            }

        return movies

    def get_movies_to_re_add(
        self,
        providers: Optional[List[str]],
        disable_progress: bool,
    ) -> Dict[int, dict]:
        """Return the movies that can be re-added."""

        if not providers:
            providers = self.config.providers

        movies = self.actions.get_movies_to_re_add(
            providers, self.config.fast_search, disable_progress
        )
        movies = {
            id: values
            for id, values in movies.items()
            if values["title"] not in self.config.radarr_excludes
        }
        return movies

    # ------------------------------------------------------------------
    # Business actions
    # ------------------------------------------------------------------
    def exclude_movies(
        self,
        movies: Dict[int, dict],
        action: Action,
        delete_files: bool,
        exclusion: bool,
        yes: bool,
    ) -> Dict[str, object]:
        """Execute the exclusion action on the provided movies.

        Parameters
        ----------
        movies:
            Dictionary as returned by :meth:`get_movies_to_exclude`.
        action:
            The :class:`Action` to execute (delete or not_monitored).
        delete_files / exclusion:
            Flags that influence how the :class:`RadarrActions` behave.
        yes:
            Skip the confirmation prompt when ``True``.

        Returns
        -------
        dict
            ``{"excluded": bool, "ids": List[int]}``
        """

        if not movies:
            return {"excluded": False, "ids": []}

        if not self._confirm(action, "movies", yes):
            logger.warning(
                "Aborting Excludarr because user did not confirm the question"
            )
            return {"excluded": False, "ids": []}

        ids = list(movies.keys())

        if action == Action.delete:
            self.actions.delete(ids, delete_files, exclusion)
        elif action == Action.not_monitored:
            movie_info = [movie["radarr_object"] for _, movie in movies.items()]
            self.actions.disable_monitored(movie_info)
            if delete_files:
                self.actions.delete_files(ids)

        return {"excluded": True, "ids": ids}

    def readd_movies(
        self, movies: Dict[int, dict], yes: bool
    ) -> Dict[str, object]:
        """Re-enable monitoring for the provided movies."""

        if not movies:
            return {"re_added": False, "ids": []}

        if not self._confirm("re-add", "movies", yes):
            logger.warning(
                "Aborting Excludarr because user did not confirm the question"
            )
            return {"re_added": False, "ids": []}

        movie_info = [movie["radarr_object"] for _, movie in movies.items()]
        self.actions.enable_monitored(movie_info)
        return {"re_added": True, "ids": list(movies.keys())}
