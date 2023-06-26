import os
import traceback

import strawberry
from fastapi import Depends
from graphql import GraphQLError
from nxtools import logging
from strawberry.dataloader import DataLoader
from strawberry.fastapi import GraphQLRouter
from strawberry.types import ExecutionContext, Info

from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.graphql.connections import (
    EventsConnection,
    ProjectsConnection,
    UsersConnection,
)
from ayon_server.graphql.dataloaders import (
    folder_loader,
    latest_version_loader,
    product_loader,
    task_loader,
    user_loader,
    version_loader,
    workfile_loader,
)
from ayon_server.graphql.nodes.common import ProductType
from ayon_server.graphql.nodes.folder import folder_from_record
from ayon_server.graphql.nodes.product import product_from_record
from ayon_server.graphql.nodes.project import ProjectNode, project_from_record
from ayon_server.graphql.nodes.representation import representation_from_record
from ayon_server.graphql.nodes.task import task_from_record
from ayon_server.graphql.nodes.user import UserAttribType, UserNode, user_from_record
from ayon_server.graphql.nodes.version import version_from_record
from ayon_server.graphql.nodes.workfile import workfile_from_record
from ayon_server.graphql.resolvers.events import get_events
from ayon_server.graphql.resolvers.links import get_links
from ayon_server.graphql.resolvers.projects import get_project, get_projects
from ayon_server.graphql.resolvers.users import get_user, get_users
from ayon_server.lib.postgres import Postgres


async def graphql_get_context(user: UserEntity = Depends(dep_current_user)) -> dict:
    """Get the current request context"""
    return {
        # Auth
        "user": user,
        # Record parsing
        "folder_from_record": folder_from_record,
        "product_from_record": product_from_record,
        "version_from_record": version_from_record,
        "representation_from_record": representation_from_record,
        "task_from_record": task_from_record,
        "user_from_record": user_from_record,
        "project_from_record": project_from_record,
        "workfile_from_record": workfile_from_record,
        # Data loaders
        "folder_loader": DataLoader(load_fn=folder_loader),
        "product_loader": DataLoader(load_fn=product_loader),
        "task_loader": DataLoader(load_fn=task_loader),
        "version_loader": DataLoader(load_fn=version_loader),
        "latest_version_loader": DataLoader(load_fn=latest_version_loader),
        "user_loader": DataLoader(load_fn=user_loader),
        "workfile_loader": DataLoader(load_fn=workfile_loader),
        # Other
        "links_resolver": get_links,
    }


#
# Query
#


@strawberry.type
class Query:
    """Ayon GraphQL Query."""

    project: ProjectNode = strawberry.field(
        description="Get a project by name",
        resolver=get_project,
    )

    projects: ProjectsConnection = strawberry.field(
        description="Get a list of projects",
        resolver=get_projects,
    )

    users: UsersConnection = strawberry.field(
        description="Get a list of users",
        resolver=get_users,
    )

    user: UserNode = strawberry.field(
        description="Get a user by name",
        resolver=get_user,
    )

    events: EventsConnection = strawberry.field(
        description="Get a list of recorded events",
        resolver=get_events,
    )

    @strawberry.field(description="Current user")
    def me(self, info: Info) -> UserNode:
        user = info.context["user"]
        return UserNode(
            name=user.name,
            active=user.active,
            updated_at=user.updated_at,
            created_at=user.created_at,
            attrib=UserAttribType(**user.attrib.dict()),
            roles=user.data.get("roles", {}),
            is_admin=user.is_admin,
            is_manager=user.is_manager,
            is_service=user.is_service,
            is_guest=False,  # TODO
            default_roles=user.data.get("defaultRoles", []),
            has_password=bool(user.data.get("password")),
            apiKeyPreview=user.data.get("apiKeyPreview"),
        )

    @strawberry.field(description="Studio-wide product type configuration")
    async def product_types(self) -> list[ProductType]:
        return [
            ProductType(
                name=row["name"],
                icon=row["data"].get("icon"),
                color=row["data"].get("color"),
            )
            async for row in Postgres.iterate(
                """SELECT name, data FROM product_types
                ORDER BY name ASC"""
            )
        ]


class AyonSchema(strawberry.Schema):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_errors(
        self,
        errors: list[GraphQLError],
        execution_context: ExecutionContext | None = None,
    ) -> None:
        for error in errors:
            tb = traceback.extract_tb(error.__traceback__)
            if not tb:
                continue
            fname, line_no, func, msg = tb[-1]
            # strip cwd from fname
            fname = fname.replace(os.getcwd(), "")
            if error.path:
                path = "/".join([str(k) for k in error.path])
            else:
                path = ""
            message = error.message
            logging.error(f"GraphQL: {fname}:{line_no} ({path}) {message}")


router: GraphQLRouter = GraphQLRouter(
    schema=AyonSchema(query=Query),
    graphiql=False,
    context_getter=graphql_get_context,
)
