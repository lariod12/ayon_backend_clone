from ayon_server import __version__

app_meta = {
    "title": "Ayon server",
    "description": "Open VFX and Animation pipeline server",
    "version": __version__,
    "contact": {
        "name": "Ynput",
        "email": "info@ynput.io",
        "url": "https://ynput.io",
    },
    "license_info": {
        "name": "Apache License 2.0",
        "url": "http://www.apache.org/licenses/",
    },
    "terms_of_service": "https://ynput.io/terms-of-service",
}


tags_meta = [
    {
        "name": "Authentication",
        "description": """
Authentication endpoints. Most of the endpoints require authentication.
This is done by passing `Authorization` header with `Bearer <token>` value.
        """,
    },
    {
        "name": "Projects",
        "description": """
Project is a collection of folders and other entities.
Each project has a unique name, which is used as its identifier.

To address an entity within the project, you need to provide
both the project name and the entity ID.
        """,
    },
    {
        "name": "Folders",
        "description": """
Endpoints for managing folders.
        """,
    },
    {
        "name": "Attributes",
        "description": """
Endpoints related to attribute configuration.

Warning: data does not reflect the active configuration of the attributes.
The server needs to be restarted in order the changes become active.
        """,
    },
    {
        "name": "Addon settings",
        "description": """
Addon configuration, site and project overrides...
        """,
    },
    {
        "name": "Secrets",
        "description": """
Sensitive information, like passwords or API keys, can be securely stored in secrets,
which are only accessible by administrators and services.
This makes them an ideal location for storing this type of data.

For addons needing access to secrets, using the 'secret name' in settings
instead of the actual value is recommended.
Consequently, updating secrets won't require any changes to the addon configuration.
""",
    },
]
