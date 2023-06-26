from typing import Any

from ayon_server.lib.postgres import Postgres


async def deploy_roles(roles: list[dict[str, Any]]) -> None:
    await Postgres.execute("DELETE FROM public.roles")
    for role in roles:
        await Postgres.execute(
            """
            INSERT INTO public.roles
                (name, data)
            VALUES
                ($1, $2)
            """,
            role["name"],
            role["data"],
        )
