from typing import Any

from nxtools import logging

from ayon_server.settings.common import BaseSettingsModel


def apply_overrides(
    settings: BaseSettingsModel,
    overrides: dict[str, Any],
) -> BaseSettingsModel:
    """Take a system settings object and apply the overrides to it.

    Overrides are a dictionary of the same structure as the settings object,
    but only the values that have been overridden are included (which is
    the way overrides are stored in the database).
    """
    result: dict[str, Any] = {}

    def crawl(
        obj: BaseSettingsModel,
        override: dict[str, Any],
        target: dict[str, Any],
    ) -> None:
        for name, _field in obj.__fields__.items():
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel):
                target[name] = {}
                crawl(child, override.get(name, {}), target[name])
            else:
                # Naive types
                if name in override:
                    try:
                        type(child)(override[name])
                    except ValueError:
                        logging.warning(f"Invalid value for {name}: {override[name]}")
                        continue
                    except TypeError:
                        # This is okay
                        pass

                    target[name] = override[name]
                else:
                    target[name] = child

    crawl(settings, overrides, result)
    return settings.__class__(**result)


def list_overrides(
    obj: BaseSettingsModel,
    override: dict[str, Any],
    crumbs: list[str] | None = None,
    level: str = "studio",
    in_group: bool = False,
) -> dict[str, Any]:
    """Returns values which are overriden.

    This is used in the settings form context.
    Return a dictionary of the form:
        {
            key : {            // idSchema of the field as used in rjsf
                "path": path,  // list of parent keys and the current key
                "type": type,  // type of the field: branch, leaf, group, array
                "value": value, // value of the field (only present on leaves)
                "level": level, // source of the override: studio, project or site
            }
        }

    """

    result = {}

    if crumbs is None:
        crumbs = []
        root = "root"
    else:
        root = "root_" + "_".join(crumbs)

    for name, _field in obj.__fields__.items():
        child = getattr(obj, name)
        path = f"{root}_{name}"
        chcrumbs = [*crumbs, name]

        if isinstance(child, BaseSettingsModel):
            if name in override:
                result[path] = {
                    "path": chcrumbs,
                    "type": "group" if child._isGroup else "branch",
                    "level": level,
                    "inGroup": in_group,
                }
            result.update(
                list_overrides(
                    child,
                    override.get(name, {}),
                    chcrumbs,
                    level,
                    in_group=child._isGroup,
                )
            )

        elif type(child) is list:
            if name in override:
                result[path] = {
                    "path": chcrumbs,
                    "type": "list",
                    "level": level,
                    "inGroup": in_group,
                }

                for i, item in enumerate(child):
                    ovr = override[name][i]
                    if isinstance(item, BaseSettingsModel):
                        result.update(
                            list_overrides(
                                item,
                                ovr,
                                [*chcrumbs, f"{i}"],
                                level=level,
                                in_group=True,
                            )
                        )
                    else:
                        result[f"{path}_{i}"] = {
                            "path": [*chcrumbs, f"{i}"],
                            "level": "default",
                            "value": item,
                            "inGroup": True,
                        }

        elif isinstance(child, tuple):
            result[path] = {
                "path": chcrumbs,
                "value": override[name] if name in override else list(child),
                "level": level if name in override else "default",
                "inGroup": in_group,
            }

        elif name in override:
            result[path] = {
                "path": chcrumbs,
                "value": override[name],
                "level": level,
                "inGroup": in_group,
            }

    return result


def extract_overrides(
    default: BaseSettingsModel,
    overriden: BaseSettingsModel,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def crawl(obj, ovr, ex, target):
        for name, _field in obj.__fields__.items():
            child = getattr(obj, name)
            if isinstance(child, BaseSettingsModel) and not child._isGroup:
                if child.dict() != ovr.dict()[name] or (name in ex):
                    target[name] = {}
                    crawl(child, getattr(ovr, name), ex.get(name, {}), target[name])
            else:
                if getattr(ovr, name) != getattr(obj, name) or (name in ex):
                    target[name] = ovr.dict()[name]

    crawl(default, overriden, existing or {}, result)
    return result
