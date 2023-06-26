from typing import Annotated

from strawberry.types import Info

from ayon_server.graphql.connections import ProjectsConnection
from ayon_server.graphql.edges import ProjectEdge
from ayon_server.graphql.nodes.project import ProjectNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    create_pagination,
    resolve,
)
from ayon_server.types import validate_name
from ayon_server.utils import SQLTool


async def get_projects(
    root,
    info: Info,
    name: Annotated[
        str | None,
        argdesc(
            """
            The name of the project to retrieve.
            If not provided, all projects will be returned.
            """
        ),
    ] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> ProjectsConnection:
    """Return a list of projects."""

    sql_conditions = []
    if name is not None:
        validate_name(name)
        sql_conditions.append(f"projects.name ILIKE '{name}'")

    #
    # Pagination
    #

    order_by = ["name"]
    pagination, paging_conds, cursor = create_pagination(
        order_by, first, after, last, before
    )
    sql_conditions.extend(paging_conds)

    #
    #
    #

    query = f"""
        SELECT {cursor}, * FROM projects
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        ProjectsConnection,
        ProjectEdge,
        ProjectNode,
        None,
        query,
        first,
        last,
        context=info.context,
    )


async def get_project(root, info: Info, name: str) -> ProjectNode | None:
    """Return a project node based on its name."""
    if not name:
        return None
    connection = await get_projects(root, info, name=name)
    if not connection.edges:
        return None
    return connection.edges[0].node
