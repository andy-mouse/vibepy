"""The composition root as a value, and the projection a reader gets from it.

A declaration holds no factory, so the pairing of a definition with a lifespan
needs an object of its own. That object is what a package names, and it is not a
declaration. See
`docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, JsonValue

from vibepy_core.app.composition import Lifespan
from vibepy_core.app.model import AppDefinition


@dataclass(frozen=True)
class ToolDescription:
    """One Tool, as a reader that cannot import the App sees it."""

    name: str
    description: str
    input_schema: Mapping[str, JsonValue]
    output_schema: Mapping[str, JsonValue]


@dataclass(frozen=True)
class PageDescription:
    """One Page, as a reader that cannot import the App sees it."""

    name: str
    route: str
    title: str


@dataclass(frozen=True)
class AppDescription:
    """One App's declarations, carrying no type parameter and no resource.

    This is what crosses a process boundary, which is why every schema is typed
    as the JSON it becomes there and nothing here is generic.
    """

    app_id: str
    name: str
    version: str
    config_schema: Mapping[str, JsonValue]
    tools: tuple[ToolDescription, ...]
    pages: tuple[PageDescription, ...]


@dataclass(frozen=True)
class AppEntrypoint[DepsT, ConfigT: BaseModel]:
    """What a package names: one definition and the lifespan that resources it."""

    definition: AppDefinition[DepsT, ConfigT]
    lifespan: Lifespan[DepsT, ConfigT]

    def describe(self) -> AppDescription:
        """Project the declarations. Reads no configuration and enters no lifespan.

        A Tool's schemas are the declaration's own, so this surface and the
        Agent channel cannot describe one model two ways.
        """
        return AppDescription(
            app_id=self.definition.app_id,
            name=self.definition.name,
            version=self.definition.version,
            config_schema=self.definition.config.model_json_schema(),
            tools=tuple(
                ToolDescription(
                    name=tool.definition.name,
                    description=tool.definition.description,
                    input_schema=tool.definition.input_schema(),
                    output_schema=tool.definition.output_schema(),
                )
                for tool in self.definition.tools
            ),
            pages=tuple(
                PageDescription(
                    name=page.definition.name,
                    route=page.definition.route,
                    title=page.definition.title,
                )
                for page in self.definition.pages
            ),
        )
