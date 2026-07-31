"""Domain model, skill store, and repositories for the Agent Skills Hub."""

from agentskills_hub_core.archives import (
    ArchiveLimits,
    UnsafeArchiveError,
    UnsupportedArchiveError,
    content_digest,
)
from agentskills_hub_core.auth import TeamPrincipal, authenticate
from agentskills_hub_core.database import (
    DEFAULT_DATABASE_URL,
    DatabaseEngine,
    DatabaseSession,
    SessionFactory,
    create_engine,
    create_session_factory,
    session_scope,
)
from agentskills_hub_core.enums import (
    SkillLifecycle,
    SkillScope,
    SubscriptionModel,
    SubscriptionOrigin,
    SubscriptionStatus,
    VersionStatus,
    Visibility,
)
from agentskills_hub_core.identifiers import (
    InvalidIdentifierError,
    validate_skill_id,
    validate_team_slug,
    validate_version,
)
from agentskills_hub_core.models import (
    ApiKey,
    Environment,
    Skill,
    SkillVersion,
    Subscription,
    Team,
)
from agentskills_hub_core.repositories import (
    DEFAULT_ENVIRONMENT_NAME,
    ApiKeyRepository,
    SkillRepository,
    SubscriptionRepository,
    TeamRepository,
)
from agentskills_hub_core.security import (
    TOKEN_SCHEME,
    MintedApiKey,
    mint_api_key,
    split_token,
    verify_secret,
)
from agentskills_hub_core.store import (
    SKILL_FILE,
    InvalidSkillArchiveError,
    LocalFileSystemSkillStore,
    PublishedVersion,
    SkillStore,
    SkillStoreError,
    VersionAlreadyPublishedError,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_DATABASE_URL",
    "DEFAULT_ENVIRONMENT_NAME",
    "SKILL_FILE",
    "TOKEN_SCHEME",
    "ApiKey",
    "ApiKeyRepository",
    "ArchiveLimits",
    "DatabaseEngine",
    "DatabaseSession",
    "Environment",
    "InvalidIdentifierError",
    "InvalidSkillArchiveError",
    "LocalFileSystemSkillStore",
    "MintedApiKey",
    "PublishedVersion",
    "SessionFactory",
    "Skill",
    "SkillLifecycle",
    "SkillRepository",
    "SkillScope",
    "SkillStore",
    "SkillStoreError",
    "SkillVersion",
    "Subscription",
    "SubscriptionModel",
    "SubscriptionOrigin",
    "SubscriptionRepository",
    "SubscriptionStatus",
    "Team",
    "TeamPrincipal",
    "TeamRepository",
    "UnsafeArchiveError",
    "UnsupportedArchiveError",
    "VersionAlreadyPublishedError",
    "VersionStatus",
    "Visibility",
    "__version__",
    "authenticate",
    "content_digest",
    "create_engine",
    "create_session_factory",
    "mint_api_key",
    "session_scope",
    "split_token",
    "validate_skill_id",
    "validate_team_slug",
    "validate_version",
    "verify_secret",
]
