from contextlib import suppress
from typing import Any

from pydantic import BaseModel

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities.core.base import BaseEntity
from ayon_server.exceptions import ConstraintViolationException, NotFoundException
from ayon_server.helpers.statuses import get_default_status_for_entity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import SQLTool, dict_exclude


class ProjectLevelEntity(BaseEntity):
    entity_type: ProjectLevelEntityType
    project_name: str

    def __init__(
        self,
        project_name: str,
        payload: dict[str, Any],
        exists: bool = False,
        validate: bool = True,  # deprecated
        own_attrib: list[str] | None = None,
    ) -> None:
        """Return a new entity instance from given data.

        When own_attrib is set to None, all attributes are
        considered entity's own. When set to list, only selected
        attributes will be stored in the attrib column, others will
        be considered inherited (and stored in exported_attribs)
        """

        attrib_dict = payload.get("attrib", {})
        if isinstance(attrib_dict, BaseModel):
            attrib_dict = attrib_dict.dict()
        if own_attrib is None:
            self.own_attrib = list(attrib_dict.keys())
        else:
            self.own_attrib = own_attrib

        self._payload = self.model.main_model(
            **dict_exclude(payload, ["own_attrib"]),
            own_attrib=self.own_attrib,
        )

        self.exists = exists
        self.project_name = project_name

    @classmethod
    def from_record(
        cls,
        project_name: str,
        payload: dict[str, Any],
        validate: bool = False,  # deprecated
        own_attrib: list[str] | None = None,
    ):
        """Return an entity instance based on a DB record.

        This factory method differs from the default constructor,
        # because it accepts a DB row data and de-serializes JSON fields
        and reformats ids.

        """
        parsed = {}
        for key in cls.model.main_model.__fields__:
            if key not in payload:
                continue  # there are optional keys too
            parsed[key] = payload[key]
        return cls(
            project_name,
            parsed,
            exists=True,
            own_attrib=own_attrib,
        )

    def replace(self, replace_data: BaseModel) -> None:
        """Replace the entity payload with new data."""
        self._payload = self.model.main_model(id=self.id, **replace_data.dict())

    #
    # Access control
    #

    def as_user(self, user):
        """Return a payload of the entity limited to the attributes that
        are accessible to the given user.
        """
        kw: dict[str, Any] = {"deep": True, "exclude": {}}

        # TODO: Clean-up. use model.attrb_model.__fields__ to create blacklist
        attrib = self._payload.attrib.dict()
        if not user.is_manager:
            kw["exclude"]["data"] = True

            attr_perm = user.permissions(self.project_name).attrib_read
            if attr_perm.enabled:
                exattr = set()
                for key in tuple(attrib.keys()):
                    if key not in attr_perm.attributes:
                        exattr.add(key)
                if exattr:
                    kw["exclude"]["attrib"] = exattr

        result = self._payload.copy(**kw)
        return result

    async def ensure_create_access(self, user) -> None:
        """Check if the user has access to create a new entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "create"
        )

    async def ensure_read_access(self, user) -> None:
        """Check if the user has access to read the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(user, self.project_name, self.entity_type, self.id)

    async def ensure_update_access(self, user) -> None:
        """Check if the user has access to update the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "update"
        )

    async def ensure_delete_access(self, user) -> None:
        """Check if the user has access to delete the entity.

        Raises FobiddenException if the user does not have access.
        """
        await ensure_entity_access(
            user, self.project_name, self.entity_type, self.id, "delete"
        )

    #
    # Database methods
    #

    @classmethod
    async def load(
        cls,
        project_name: str,
        entity_id: str,
        transaction=None,
        for_update=False,
    ):
        """Return an entity instance based on its ID and a project name.

        Raise ValueError if project_name or base_id is not valid.
        Raise KeyError if the folder does not exists.

        Set for_update=True and pass a transaction to lock the row
        for update.
        """

        query = f"""
            SELECT  *
            FROM project_{project_name}.{cls.entity_type}s
            WHERE id=$1
            {'FOR UPDATE' if transaction and for_update else ''}
            """

        async for record in Postgres.iterate(query, entity_id):
            return cls.from_record(project_name, record)
        raise NotFoundException("Entity not found")

    #
    # Save
    #

    async def pre_save(self, insert: bool, transaction) -> None:
        """Hook called before saving the entity to the database."""
        pass

    async def save(self, transaction=None) -> bool:
        """Save the entity to the database.

        Supports both creating and updating. Entity must be loaded from the
        database in order to update. If the entity is not loaded, it will be
        created.

        Returns True if the folder was successfully saved.

        Optional `transaction` argument may be specified to pass a connection object,
        to run the query in (to run multiple transactions). When used,
        Entity.commit method is not called automatically and it is expected
        it is called at the end of the transaction block.
        """

        commit = not transaction
        transaction = transaction or Postgres

        if self.status is None:
            self.status = await self.get_default_status()

        attrib = {}
        for key in self.own_attrib:
            with suppress(AttributeError):
                if (value := getattr(self.attrib, key)) is not None:
                    attrib[key] = value

        if self.exists:
            # Update existing entity

            fields = dict_exclude(
                self.dict(exclude_none=True),
                ["id", "ctime"] + self.model.dynamic_fields,
            )
            fields["attrib"] = attrib

            try:
                await self.pre_save(False, transaction)
                await transaction.execute(
                    *SQLTool.update(
                        f"project_{self.project_name}.{self.entity_type}s",
                        f"WHERE id = '{self.id}'",
                        **fields,
                    )
                )
            except Postgres.ForeignKeyViolationError as e:
                raise ConstraintViolationException(e.detail)

            except Postgres.UniqueViolationError as e:
                raise ConstraintViolationException(e.detail)

            if commit:
                await self.commit(transaction)
            return True

        # Create a new entity
        try:
            fields = dict_exclude(
                self.dict(exclude_none=True),
                self.model.dynamic_fields,
            )
            fields["attrib"] = attrib

            await self.pre_save(True, transaction)
            await transaction.execute(
                *SQLTool.insert(
                    f"project_{self.project_name}.{self.entity_type}s",
                    **fields,
                )
            )
        except Postgres.ForeignKeyViolationError as e:
            raise ConstraintViolationException(e.detail)

        except Postgres.UniqueViolationError as e:
            raise ConstraintViolationException(e.detail)

        if commit:
            await self.commit(transaction)
        return True

    #
    # Delete
    #

    async def delete(self, transaction=None) -> bool:
        """Delete an existing entity."""
        if not self.id:
            raise NotFoundException(f"Unable to delete unloaded {self.entity_type}.")

        commit = not transaction
        transaction = transaction or Postgres
        try:
            res = await transaction.fetch(
                f"""
                WITH deleted AS (
                    DELETE FROM project_{self.project_name}.{self.entity_type}s
                    WHERE id=$1
                    RETURNING *
                ) SELECT count(*) FROM deleted;
                """,
                self.id,
            )
            count = res[0]["count"]
        except Postgres.ForeignKeyViolationError as e:
            detail = f"Unable to delete {self.entity_type} {self.id}"
            if self.entity_type == "folder":
                _ = e  # TODO: use this
                detail = "Unable to delete a folder with products or tasks."
            raise ConstraintViolationException(detail)

        if commit:
            await self.commit(transaction)
        return bool(count)

    async def get_default_status(self) -> str:
        return await get_default_status_for_entity(
            self.project_name,
            self.entity_type,
            self.entity_subtype,
        )

    #
    # Properties
    #

    @property
    def id(self) -> str:
        """Return the entity id."""
        return self._payload.id

    @id.setter
    def id(self, value: str):
        """Set the entity id."""
        self._payload.id = value

    @property
    def parent_id(self) -> str | None:
        """Return the parent id.

        Return None if the entity does not have a parent.
        In case of tasks and products, this is the folder id,
        in case of folders, this is the parent folder id,
        and so on...
        """
        raise NotImplementedError

    @property
    def status(self) -> str:
        """Return the entity status."""
        return self._payload.status

    @status.setter
    def status(self, value: str):
        """Set the entity status."""
        self._payload.status = value

    @property
    def tags(self) -> list[str]:
        return self._payload.tags

    @tags.setter
    def tags(self, value: list[str]):
        self._payload.tags = value

    @property
    def entity_subtype(self) -> str | None:
        """Return the entity subtype.

        For folders and tasks this is the folder type or task type.
        For other entities this is None.
        """
        return None
