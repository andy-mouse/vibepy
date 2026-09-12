"""The composition root as a value, and the projection a reader gets from it."""

from dataclasses import dataclass

from pydantic import BaseModel, JsonValue

from vibepy_core.app.composition import Lifespan
from vibepy_core.app.config import AppConfig, ConfigFieldDescription, config_fields_of
from vibepy_core.app.model import AppDefinition
from vibepy_core.channel import Channel


class ToolDescription(BaseModel):
    """One Tool, as a reader that cannot import the App sees it."""

    name: str
    description: str
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    read_only: bool
    channels: list[Channel]
    required_roles: list[str]


class PageDescription(BaseModel):
    """One Page, as a reader that cannot import the App sees it."""

    name: str
    route: str
    title: str


class AppDescription(BaseModel):
    """One App's declarations, carrying no type parameter and no resource.

    This is what crosses a process boundary, which is why it is one model a
    writer dumps and a reader validates, every schema is typed as the JSON it
    becomes there, and nothing here is generic.
    """

    app_id: str
    name: str
    version: str
    config_schema: dict[str, JsonValue]
    config_fields: list[ConfigFieldDescription]
    tools: list[ToolDescription]
    pages: list[PageDescription]


class DescribedApp(BaseModel):
    """One entry of what `describe` writes: the declaration's identity, and its description.

    It lives beside the `AppDescription` it wraps rather than with the command
    that transports it, per `docs/architecture/app-model.md` "The import surface".
    """

    app_name: str
    distribution: str
    distribution_version: str
    description: AppDescription


@dataclass(frozen=True, kw_only=True)
class AppEntrypoint[DepsT, ConfigT: AppConfig]:
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
            config_fields=config_fields_of(self.definition.config),
            tools=[
                ToolDescription(
                    name=tool.definition.name,
                    description=tool.definition.description,
                    input_schema=tool.definition.input_schema(),
                    output_schema=tool.definition.output_schema(),
                    read_only=tool.definition.read_only,
                    channels=sorted(tool.definition.channels),
                    required_roles=sorted(tool.definition.required_roles),
                )
                for tool in self.definition.tools
            ],
            pages=[
                PageDescription(
                    name=page.definition.name,
                    route=page.definition.route,
                    title=page.definition.title,
                )
                for page in self.definition.pages
            ],
        )
