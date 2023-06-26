from ayon_server.entities.core import ProjectLevelEntity, attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.types import ProjectLevelEntityType


class ProductEntity(ProjectLevelEntity):
    entity_type: ProjectLevelEntityType = "product"
    model = ModelSet("product", attribute_library["product"])

    #
    # Properties
    #

    async def pre_save(self, insert, transaction) -> None:
        """Hook called before saving the entity to the database."""
        await transaction.execute(
            """
            INSERT INTO product_types (name)
            VALUES ($1)
            ON CONFLICT DO NOTHING
            """,
            self.product_type,
        )

    @property
    def folder_id(self) -> str:
        return self._payload.folder_id

    @folder_id.setter
    def folder_id(self, value: str):
        self._payload.folder_id = value

    @property
    def parent_id(self) -> str:
        return self.folder_id

    @property
    def product_type(self) -> str:
        return self._payload.product_type

    @product_type.setter
    def product_type(self, value: str):
        self._payload.product_type = value
