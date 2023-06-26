from fastapi import APIRouter

from ayon_server.api import ResponseFactory

route_meta = {
    "tags": ["Addon settings"],
}

router = APIRouter(
    prefix="/addons",
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)
