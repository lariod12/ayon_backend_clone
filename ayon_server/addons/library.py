import os
from typing import ItemsView

from nxtools import log_traceback, logging

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.definition import ServerAddonDefinition
from ayon_server.config import ayonconfig

# from ayon_server.addons.utils import classes_from_module, import_module
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres


class AddonLibrary:
    ADDONS_DIR = ayonconfig.addons_dir
    _instance = None

    @classmethod
    def getinstance(cls) -> "AddonLibrary":
        if cls._instance is None:
            cls._instance = AddonLibrary()
        return cls._instance

    def __init__(self) -> None:
        self.data = {}
        self.restart_requested = False
        addons_dir = self.get_addons_dir()
        if addons_dir is None:
            logging.error(f"Addons directory does not exist: {addons_dir}")
            return None

        for addon_name in os.listdir(addons_dir):
            # ignore hidden directories (such as .git)
            if addon_name.startswith("."):
                continue

            addon_dir = os.path.join(addons_dir, addon_name)
            if not os.path.isdir(addon_dir):
                continue

            try:
                definition = ServerAddonDefinition(self, addon_dir)
            except Exception:
                log_traceback(f"Unable to initialize {addon_dir}")
                continue
            if not definition.versions:
                continue

            logging.info("Initializing addon", definition.name)
            self.data[definition.name] = definition
            if definition.restart_requested:
                self.restart_requested = True

    def get_addons_dir(self) -> str | None:
        for d in [ayonconfig.addons_dir, "addons"]:
            if not os.path.isdir(d):
                continue
            return d
        return None

    @classmethod
    def addon(cls, name: str, version: str) -> BaseServerAddon:
        """Return an instance of the given addon.

        Raise NotFoundException if the addon is not found.
        """

        instance = cls.getinstance()
        if (definition := instance.get(name)) is None:
            raise NotFoundException(f"Addon {name} does not exist")
        if (addon := definition.versions.get(version)) is None:
            raise NotFoundException(f"Addon {name} version {version} does not exist")
        return addon

    @classmethod
    def items(cls) -> ItemsView[str, ServerAddonDefinition]:
        instance = cls.getinstance()
        return instance.data.items()

    def get(self, key: str, default=None) -> ServerAddonDefinition:
        return self.data.get(key, default)

    def __getitem__(self, key) -> ServerAddonDefinition:
        return self.data[key]

    def __contains__(self, key) -> bool:
        return key in self.data

    def __iter__(self):
        return iter(self.data)

    async def get_active_versions(self) -> dict[str, dict[str, str]]:
        active_versions = {}
        async for row in Postgres.iterate("SELECT * FROM addon_versions"):
            active_versions[row["name"]] = {
                "production": row["production_version"],
                "staging": row["staging_version"],
            }
        return active_versions

    async def get_production_addon(self, addon_name: str) -> BaseServerAddon | None:
        """Return a production instance of the addon."""
        active_versions = await self.get_active_versions()
        if addon_name not in active_versions:
            return None
        production_version = active_versions[addon_name]["production"]
        if production_version is None:
            return None
        return self[addon_name][production_version]

    async def get_staging_addon(self, addon_name: str) -> BaseServerAddon | None:
        """Return a staging instance of the addon."""
        active_versions = await self.get_active_versions()
        if addon_name not in active_versions:
            return None
        staging_version = active_versions[addon_name]["staging"]
        if staging_version is None:
            return None
        return self[addon_name][staging_version]
