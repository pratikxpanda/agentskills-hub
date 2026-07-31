"""Catalog, publishing, subscription, and authentication API for the Agent Skills Hub."""

__version__ = "0.1.0"

# create_app lives in agentskills_hub_api.app: importing it here would make every consumer of
# __version__ pay for FastAPI.
__all__ = ["__version__"]
