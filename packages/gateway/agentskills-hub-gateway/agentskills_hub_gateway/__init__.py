"""Multi-tenant MCP endpoint serving each team its subscribed Agent Skills."""

from agentskills_hub_gateway.app import create_gateway_app
from agentskills_hub_gateway.composition import ComposedRegistry, compose
from agentskills_hub_gateway.settings import GatewaySettings

__version__ = "0.1.0"

__all__ = [
    "ComposedRegistry",
    "GatewaySettings",
    "__version__",
    "compose",
    "create_gateway_app",
]
