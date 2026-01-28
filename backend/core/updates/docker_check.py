import aiohttp

from app_logger import ModuleLogger
from config.settings import app_settings

logger = ModuleLogger("UpdateChecker")


async def get_latest_image_version(image_name: str) -> str | None:
    """Gets the latest release tag from Github API asynchronously.
    Args:
        image_name (str): The name of the Docker image on Docker Hub. \n
            Example: "library/ubuntu" \n
    Returns:
        str|None: The latest release tag of the image.\n
            Example: "v0.2.0"
    """
    url = f"https://api.github.com/repos/{image_name}/releases/latest"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                release_data = await response.json()
                return release_data["tag_name"]
    except Exception as e:
        logger.error(f"Error fetching release info from Github API: {e}")
        return None


def get_current_image_version() -> str:
    """Gets the current version of the app running in the container."""
    return app_settings.version


async def check_for_update() -> None:
    """Check for updates to the Docker image.
    Returns:
        None
    """
    image_name = "nandyalu/trailarr"
    current_version = get_current_image_version()
    logger.info(f"Current version of Trailarr: {current_version}")
    latest_version = await get_latest_image_version(image_name)

    if not latest_version:
        return

    if current_version != latest_version:
        logger.info(
            f"A newer version ({latest_version}) of Trailarr is available."
            " Please update!"
        )
        app_settings.update_available = True
    else:
        logger.info(
            f"You are using the latest version ({latest_version}) of Trailarr."
        )


async def check_for_updates():
    """Check for updates to the Docker image."""
    await check_for_update()


# if __name__ == "__main__":
#     asyncio.run(check_for_updates())
