import asyncio
import collections
import functools
import threading
from typing import Any, DefaultDict

from ayon_server.lib.postgres import Postgres


class AttributeLibrary:
    """Dynamic attributes loader class.

    This is very wrong and i deserve a punishment for this,
    but it works. Somehow. It needs to be initialized when
    this module is loaded and it has to load the attributes
    from the database in blocking mode regardless the running
    event loop. So it connects to the DB independently in a
    different thread and waits until it is finished.

    Attribute list for each entity type may be then accessed
    using __getitem__ method.
    """

    def __init__(self) -> None:
        self.data: DefaultDict[str, Any] = collections.defaultdict(list)

        # Used in info endpoint to get the active list of attributes
        # in the same format as the attributes endpoint
        self.info_data: list[Any] = []
        _thread = threading.Thread(target=self.execute)
        _thread.start()
        _thread.join()

    def execute(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.load())
        loop.close()

    def is_valid(self, entity_type: str, attribute: str) -> bool:
        """Check if attribute is valid for entity type."""
        return attribute in [k["name"] for k in self.data[entity_type]]

    async def load(self) -> None:
        query = "SELECT * FROM public.attributes ORDER BY position"
        await Postgres.connect()
        async for row in Postgres.iterate(query):
            self.info_data.append(row)
            for scope in row["scope"]:
                attrd = {"name": row["name"], **row["data"]}
                # Only project attributes should have defaults.
                # All the others are nullable and should inherit from
                # their parent entities
                if (scope != "project") and ("default" in attrd):
                    del attrd["default"]
                self.data[scope].append(attrd)

    def __getitem__(self, key) -> list[dict[str, Any]]:
        return self.data[key]

    @functools.cache
    def inheritable_attributes(self) -> list[str]:
        result = set()
        for entity_type in self.data:
            for attr in self.data[entity_type]:
                if attr.get("inherit", True):
                    result.add(attr["name"])
        return list(result)

    @functools.cache
    def by_name(self, name: str) -> dict[str, Any]:
        """Return attribute definition by name."""
        for entity_type in self.data:
            for attr in self.data[entity_type]:
                if attr["name"] == name:
                    return attr
        raise KeyError(f"Attribute {name} not found")


attribute_library = AttributeLibrary()
