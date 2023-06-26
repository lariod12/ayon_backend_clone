from fastapi import APIRouter, BackgroundTasks, Header

from ayon_server.api.dependencies import CurrentUser, FolderID, ProjectName
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.config import ayonconfig
from ayon_server.entities import FolderEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres

router = APIRouter(prefix="/projects/{project_name}/folders", tags=["Folders"])

#
# [GET]
#


@router.get("/{folder_id}", response_model_exclude_none=True)
async def get_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
) -> FolderEntity.model.main_model:  # type: ignore
    """Retrieve a folder by its ID."""

    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_read_access(user)
    return folder.as_user(user)


#
# [POST]
#


@router.post("", status_code=201)
async def create_folder(
    post_data: FolderEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EntityIdResponse:
    """Create a new folder."""

    folder = FolderEntity(project_name=project_name, payload=post_data.dict())
    await folder.ensure_create_access(user)
    event = {
        "topic": "entity.folder.created",
        "description": f"Folder {folder.name} created",
        "summary": {"entityId": folder.id, "parentId": folder.parent_id},
        "project": project_name,
    }
    if ayonconfig.audit_trail:
        event["payload"] = {
            "newValue": folder.payload.dict(exclude_none=True),
        }

    await folder.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=folder.id)


#
# [PATCH]
#


@router.patch("/{folder_id}", status_code=204)
async def update_folder(
    post_data: FolderEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Patch (partially update) a folder.

    Once there is a version published, the folder's name and hierarchy
    cannot be changed.
    """

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            folder = await FolderEntity.load(
                project_name, folder_id, transaction=conn, for_update=True
            )

            await folder.ensure_update_access(user)
            has_versions = bool(await folder.get_versions(conn))

            # If the folder has versions, we can't update the name,
            # folder_type or change the hierarchy
            for key in ("name", "folder_type", "parent_id"):
                old_value = folder.payload.dict(exclude_none=True).get(key)
                new_value = post_data.dict(exclude_none=None).get(key)

                if (new_value is None) or (old_value == new_value):
                    continue

                if has_versions:
                    raise ForbiddenException(
                        f"Cannot update {key} folder with published versions"
                    )

            events = build_pl_entity_change_events(folder, post_data)

            folder.patch(post_data)
            await folder.save(transaction=conn)
            await folder.commit(conn)

    for event in events:
        background_tasks.add_task(
            dispatch_event,
            sender=x_sender,
            user=user.name,
            **event,
        )

    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Delete a folder."""

    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_delete_access(user)
    event = {
        "topic": "entity.folder.deleted",
        "description": f"Folder {folder.name} deleted",
        "summary": {"entityId": folder.id, "parentId": folder.parent_id},
        "project": project_name,
    }
    if ayonconfig.audit_trail:
        event["payload"] = {
            "originalValue": folder.payload.dict(exclude_none=True),
        }

    await folder.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EmptyResponse()
