import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter

from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel

from .templating import StringTemplate

router = APIRouter(tags=["URI resolver"])


class ResolveRequestModel(OPModel):
    uris: list[str] = Field(
        ...,
        title="URIs",
        description="List of uris to resolve",
        example=[
            "ayon+entity://demo_Big_Feature/assets/environments/01_pfueghtiaoft?product=layoutMain&version=v004"
        ],
    )


class ResolvedEntityModel(OPModel):
    project_name: str = Field(
        ...,
        title="Project name",
        example="demo_Big_Feature",
    )
    folder_id: str | None = Field(
        None,
        title="Folder id",
        example="0254c370005811ee9a740242ac130004",
    )
    product_id: str | None = Field(
        None,
        title="Product id",
        example="0255ce50005811ee9a740242ac130004",
    )
    task_id: str | None = Field(
        None,
        title="Task id",
        example=None,
    )
    version_id: str | None = Field(
        None,
        title="Version id",
        example="0256ba2c005811ee9a740242ac130004",
    )
    representation_id: str | None = Field(
        None,
        title="Representation id",
        example=None,
    )
    workfile_id: str | None = Field(
        None,
        title="Workfile id",
        example=None,
    )
    file_path: str | None = Field(
        None,
        title="File path",
        description="Path to the file if a representation is specified",
        example="/path/to/file.ma",
    )


class ResolvedURIModel(OPModel):
    uri: str = Field(
        ...,
        title="Resolved URI",
        example="ayon+entity://demo_Big_Feature/assets/environments/01_pfueghtiaoft?product=layoutMain&version=v004",
    )
    entities: list[ResolvedEntityModel] = Field(
        ...,
        title="Resolved entities",
        example=[
            {
                "project_name": "demo_Big_Feature",
                "folder_id": "0254c370005811ee9a740242ac130004",
                "product_id": "0255ce50005811ee9a740242ac130004",
                "task_id": None,
                "version_id": "0256ba2c005811ee9a740242ac130004",
                "representation_id": None,
                "workfile_id": None,
            }
        ],
    )


class ParsedURIModel(OPModel):
    uri: str = Field(..., title="Resolved URI")
    project_name: str = Field(..., title="Project name")
    path: str | None = Field(None, title="Path")
    product_name: str | None = Field(None, title="Product name")
    task_name: str | None = Field(None, title="Task name")
    version_name: str | None = Field(None, title="Version name")
    representation_name: str | None = Field(None, title="Representation name")
    workfile_name: str | None = Field(None, title="Workfile name")


def validate_name(name: str) -> None:
    if name is None:
        return
    if name == "*":
        return
    name_validator = re.compile(NAME_REGEX)
    assert name_validator.match(name), f"Invalid name: {name}"


def parse_uri(uri: str) -> ParsedURIModel:
    project_name: str
    path: str | None
    product_name: str | None
    task_name: str | None
    version_name: str | None
    representation_name: str | None
    workfile_name: str | None

    parsed_uri = urlparse(uri)
    assert parsed_uri.scheme in [
        "ayon",
        "ayon+entity",
    ], f"Invalid scheme: {parsed_uri.scheme}"

    project_name = parsed_uri.netloc
    name_validator = re.compile(NAME_REGEX)
    assert name_validator.match(project_name), f"Invalid project name: {project_name}"

    path = parsed_uri.path.strip("/") or None

    qs: dict[str, Any] = parse_qs(parsed_uri.query)

    product_name = qs.get("product", [None])[0]
    if product_name is not None:
        validate_name(product_name)

    task_name = qs.get("task", [None])[0]
    if task_name is not None:
        validate_name(task_name)

    version_name = qs.get("version", [None])[0]
    if version_name is not None:
        validate_name(version_name)

    representation_name = qs.get("representation", [None])[0]
    if representation_name is not None:
        validate_name(representation_name)

    workfile_name = qs.get("workfile", [None])[0]
    if workfile_name is not None:
        validate_name(workfile_name)

    # assert we don't have incompatible arguments

    if task_name is not None or workfile_name is not None:
        assert product_name is None, "Tasks cannot be queried with products"
        assert version_name is None, "Tasks cannot be queried with versions"
        assert (
            representation_name is None
        ), "Tasks cannot be queried with representations"

    return ParsedURIModel(
        uri=uri,
        project_name=project_name,
        path=path,
        product_name=product_name,
        task_name=task_name,
        version_name=version_name,
        representation_name=representation_name,
        workfile_name=workfile_name,
    )


def get_representation_path(template: str, context: dict[str, Any]) -> str:
    context["root"] = {}
    return StringTemplate.format_template(template, context)


def get_path_conditions(path: str | None) -> list[str]:
    if path is None:
        return []
    if path == "*":
        return []
    return [f"h.path = '{path}'"]


def get_product_conditions(product_name: str | None) -> list[str]:
    if product_name is None:
        return []
    if product_name == "*":
        return []
    return [f"s.name = '{product_name}'"]


def get_version_conditions(version_name: str | None) -> list[str]:
    if version_name is None:
        return []
    if version_name == "*":
        return []
    if version_name.startswith("v"):
        version_name = version_name[1:]
        return [f"v.version = {int(version_name)}"]
    if version_name == "latest":
        return [
            """
            v.id in (
                SELECT l.ids[array_upper(l.ids, 1)]
                FROM version_list AS l
            )
        """
        ]
    if version_name == "hero":
        return ["v.version < 0"]

    return []


def get_representation_conditions(representation_name: str | None) -> list[str]:
    if representation_name is None:
        return []
    if representation_name == "*":
        return []
    return [f"r.name = '{representation_name}'"]


async def resolve_entities(conn, req: ParsedURIModel) -> list[ResolvedEntityModel]:
    result = []
    cols = ["h.id as folder_id"]
    joins = []
    conds = []

    print(req)
    # if not req.path:
    #     return [ResolvedEntityModel(project_name=req.project_name)]

    if req.task_name is not None or req.workfile_name is not None:
        cols.append("t.id as task_id")
        joins.append("INNER JOIN tasks AS t ON h.id = t.folder_id")
        conds.append(f"t.name = '{req.task_name}'")
        if req.workfile_name is not None:
            cols.append("w.id as workfile_id")
            joins.append("INNER JOIN workfiles AS w ON t.id = w.task_id")
            conds.append(f"w.name = '{req.workfile_name}'")

        conds.extend(get_path_conditions(req.path))

    else:
        if req.representation_name is not None:
            cols.extend(
                [
                    "s.id as product_id",
                    "v.id as version_id",
                    "r.id as representation_id",
                    "r.attrib->>'template' as file_template",
                    "r.data->'context' as context",
                ]
            )
            joins.append("INNER JOIN products AS s ON h.id = s.folder_id")
            joins.append("INNER JOIN versions AS v ON s.id = v.product_id")
            joins.append("INNER JOIN representations AS r ON v.id = r.version_id")
            conds.extend(get_representation_conditions(req.representation_name))
            conds.extend(get_version_conditions(req.version_name))
            conds.extend(get_product_conditions(req.product_name))
            conds.extend(get_path_conditions(req.path))

        elif req.version_name is not None:
            cols.extend(["s.id as product_id", "v.id as version_id"])
            joins.append("INNER JOIN products AS s ON h.id = s.folder_id")
            joins.append("INNER JOIN versions AS v ON s.id = v.product_id")
            conds.extend(get_version_conditions(req.version_name))
            conds.extend(get_product_conditions(req.product_name))
            conds.extend(get_path_conditions(req.path))

        elif req.product_name is not None:
            cols.append("s.id as product_id")
            joins.append("INNER JOIN products AS s ON h.id = s.folder_id")
            conds.extend(get_product_conditions(req.product_name))
            conds.extend(get_path_conditions(req.path))

        else:
            conds.extend(get_path_conditions(req.path))

    query = f"""
        SELECT {", ".join(cols)}
        FROM hierarchy h {" ".join(joins)}
    """
    if conds:
        query += f""" WHERE {" AND ".join(conds)}"""

    query += " LIMIT 1000"

    statement = await conn.prepare(query)
    async for row in statement.cursor():
        if "file_template" in row:
            file_path = get_representation_path(
                row["file_template"],
                row["context"],
            )
        else:
            file_path = None

        result.append(
            ResolvedEntityModel(
                project_name=req.project_name,
                file_path=file_path,
                **row,
            )
        )

    return result


@router.post("/resolve", response_model_exclude_none=True)
async def resolve_uris(request: ResolveRequestModel) -> list[ResolvedURIModel]:
    result: list[ResolvedURIModel] = []
    current_project = ""
    async with Postgres.acquire() as conn:
        async with conn.transaction():
            for uri in request.uris:
                parsed_uri = parse_uri(uri)
                if parsed_uri.project_name != current_project:
                    await conn.execute(
                        f"SET LOCAL search_path TO project_{parsed_uri.project_name}"
                    )
                    current_project = parsed_uri.project_name
                entities = await resolve_entities(conn, parsed_uri)
                result.append(ResolvedURIModel(uri=uri, entities=entities))
    return result
