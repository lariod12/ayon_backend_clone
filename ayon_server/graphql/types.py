import strawberry


@strawberry.type
class PageInfo:
    has_next_page: bool = False
    has_previous_page: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None


@strawberry.type
class BaseConnection:
    page_info: PageInfo = strawberry.field(
        default_factory=PageInfo, description="Pagination information"
    )


@strawberry.type
class BaseEdge:
    pass
