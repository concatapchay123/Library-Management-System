"""Configuration values supplied when the application is created."""

from collections.abc import Callable
from dataclasses import dataclass

ReadinessProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Dependencies needed to create an application instance."""

    readiness_probe: ReadinessProbe
