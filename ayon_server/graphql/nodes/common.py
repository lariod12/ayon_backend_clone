from datetime import datetime

import strawberry
from strawberry.types import Info

from ayon_server.graphql.types import BaseConnection, BaseEdge


@strawberry.type
class ProductType(BaseEdge):
    name: str = strawberry.field()
    icon: str | None = strawberry.field(default=None)
    color: str | None = strawberry.field(default=None)


@strawberry.type
class LinkEdge(BaseEdge):
    id: str = strawberry.field()
    project_name: str = strawberry.field()
    entity_type: str = strawberry.field()
    entity_id: str = strawberry.field()
    link_type: str = strawberry.field(default="something")
    direction: str = strawberry.field(default="in")
    description: str = strawberry.field(default="")
    author: str | None = strawberry.field(default=None)
    cursor: str | None = strawberry.field(default=None)

    @strawberry.field(description="Linked node")
    async def node(self, info: Info) -> "BaseNode":
        if self.entity_type == "folder":
            loader = info.context["folder_loader"]
            parser = info.context["folder_from_record"]
        elif self.entity_type == "version":
            loader = info.context["version_loader"]
            parser = info.context["version_from_record"]
        elif self.entity_type == "product":
            loader = info.context["product_loader"]
            parser = info.context["product_from_record"]
        elif self.entity_type == "task":
            loader = info.context["task_loader"]
            parser = info.context["task_from_record"]
        else:
            raise ValueError
        record = await loader.load((self.project_name, self.entity_id))
        return parser(self.project_name, record, info.context)


@strawberry.type
class LinksConnection(BaseConnection):
    edges: list[LinkEdge] = strawberry.field(default_factory=list)


@strawberry.interface
class BaseNode:
    project_name: str = strawberry.field()

    id: str = strawberry.field()
    name: str = strawberry.field()

    active: bool = strawberry.field()
    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()

    @strawberry.field
    async def links(
        self,
        info: Info,
        direction: str | None = None,
        link_types: list[str] = [],
        first: int = 100,
        after: str | None = None,
    ) -> LinksConnection:
        resolver = info.context["links_resolver"]
        return await resolver(
            root=self,
            info=info,
            direction=direction,
            link_types=link_types,
            first=first,
            after=after,
        )
