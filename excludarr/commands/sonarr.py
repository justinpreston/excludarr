import rich
import typer

from typing import List, Optional
from loguru import logger

import excludarr.utils.output as output

from excludarr.services.sonarr_service import SonarrService
from excludarr.utils.config import Config
from excludarr.utils.enums import Action

app = typer.Typer()


@app.command(help="Exclude TV shows in Sonarr by deleting or not monitoring them")
def exclude(
    providers: Optional[List[str]] = typer.Option(
        None,
        "-p",
        "--provider",
        metavar="PROVIDER",
        help="Override the configured streaming providers.",
    ),
    locale: Optional[str] = typer.Option(
        None, "-l", "--locale", metavar="LOCALE", help="Your locale e.g: en_US."
    ),
    action: Action = typer.Option(..., "-a", "--action", help="Change the status in Radarr."),
    delete_files: bool = typer.Option(
        False, "-d", "--delete-files", help="Delete already downloaded files."
    ),
    exclusion: bool = typer.Option(
        False, "-e", "--exclusion", help="Add an exclusion to prevent auto importing."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto accept the confirmation notice."),
    progress: bool = typer.Option(
        False, "--progress", help="Track the progress using a progressbar."
    ),
):
    # Debug logging
    logger.debug("Got exclude as subcommand")
    logger.debug(f"Got CLI values for -p, --provider option: {', '.join(providers)}")
    logger.debug(f"Got CLI values for -l, --locale option: {locale}")
    logger.debug(f"Got CLI values for -a, --action option: {action}")
    logger.debug(f"Got CLI values for -d, --delete option: {delete_files}")
    logger.debug(f"Got CLI values for -e, --exclusion option: {exclusion}")
    logger.debug(f"Got CLI values for -y, --yes option: {yes}")
    logger.debug(f"Got CLI values for --progress option: {progress}")

    # Disable the progress bar when debug logging is active
    if loglevel == 10:
        disable_progress = True
    elif progress and loglevel != 10:
        disable_progress = False
    else:
        disable_progress = True

    # Determine if CLI options should overwrite configuration settings
    if not providers:
        providers = config.providers
    if not locale:
        locale = config.locale

    # Setup Sonarr service and gather data
    service = SonarrService(config, locale)
    series_to_exclude = service.get_series_to_exclude(
        providers, action, delete_files, disable_progress
    )

    series_to_exclude_ids = list(series_to_exclude.keys())

    if series_to_exclude_ids:
        total_filesize = sum(
            [serie["filesize"] for _, serie in series_to_exclude.items()]
        )
        output.print_series_to_exclude(series_to_exclude, total_filesize)

        result = service.exclude_series(
            series_to_exclude, action, delete_files, exclusion, yes
        )
        if result["excluded"]:
            output.print_success_exclude(action, "series")
    else:
        rich.print(
            "There are no more series also available on the configured streaming providers!"
        )


@app.command(help="Change status of series to monitored if no provider is found")
def re_add(
    providers: Optional[List[str]] = typer.Option(
        None,
        "-p",
        "--provider",
        metavar="PROVIDER",
        help="Override the configured streaming providers.",
    ),
    locale: Optional[str] = typer.Option(
        None, "-l", "--locale", metavar="LOCALE", help="Your locale e.g: en_US."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto accept the confirmation notice."),
    progress: bool = typer.Option(
        False, "--progress", help="Track the progress using a progressbar."
    ),
):
    # Debug logging
    logger.debug("Got exclude as subcommand")
    logger.debug(f"Got CLI values for -p, --provider option: {', '.join(providers)}")
    logger.debug(f"Got CLI values for -l, --locale option: {locale}")
    logger.debug(f"Got CLI values for -y, --yes option: {yes}")
    logger.debug(f"Got CLI values for --progress option: {progress}")

    # Disable the progress bar when debug logging is active
    if loglevel == 10:
        disable_progress = True
    elif progress and loglevel != 10:
        disable_progress = False
    else:
        disable_progress = True

    # Determine if CLI options should overwrite configuration settings
    if not providers:
        providers = config.providers
    if not locale:
        locale = config.locale

    service = SonarrService(config, locale)
    series_to_re_add = service.get_series_to_re_add(providers, disable_progress)

    series_to_re_add_ids = list(series_to_re_add.keys())

    if series_to_re_add_ids:
        output.print_series_to_re_add(series_to_re_add)
        result = service.readd_series(series_to_re_add, yes)
        if result["re_added"]:
            rich.print(
                "Succesfully changed the status of the series listed in Sonarr to monitored!"
            )
    else:
        rich.print("There are no more series to re-add!")


@app.callback()
def init():
    """Initializes the command. Reads the configuration."""
    logger.debug("Got sonarr as subcommand")

    global config
    global loglevel

    loglevel = logger._core.min_level
    logger.debug("Reading configuration file")
    config = Config()


if __name__ == "__main__":
    app()
