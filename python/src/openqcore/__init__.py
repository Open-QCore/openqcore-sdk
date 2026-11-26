"""Official Python SDK for the OpenQCore API.

    from openqcore import OpenQCore

    client = OpenQCore()  # reads OPENQCORE_API_KEY
    session = client.sessions.create(title="Support")
    for chunk in client.chat.stream(session_id=session.id, message="Hello"):
        print(chunk.content or "", end="", flush=True)
"""

from ._client import AsyncOpenQCore, OpenQCore
from ._errors import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    GatewayTimeoutError,
    GoneError,
    InsufficientBalanceError,
    InternalServerError,
    NotFoundError,
    OpenQCoreError,
    PayloadTooLargeError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    StreamError,
    UnprocessableEntityError,
    UnsupportedMediaTypeError,
)
from ._models import (
    ApiKey,
    ArchiveList,
    ArchiveUnit,
    ChatChunk,
    ChatCompletion,
    Job,
    KnowledgeAnswer,
    KnowledgeItem,
    KnowledgeList,
    Message,
    MessageList,
    Model,
    ModelInfo,
    ModelList,
    OCRResult,
    Session,
    SessionList,
    Token,
    VoiceEvent,
)
from ._streaming import AsyncStream, Stream
from ._version import __version__

__all__ = [
    "OpenQCore",
    "AsyncOpenQCore",
    "Stream",
    "AsyncStream",
    "__version__",
    # errors
    "OpenQCoreError",
    "APIError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "BadRequestError",
    "AuthenticationError",
    "InsufficientBalanceError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "GoneError",
    "PayloadTooLargeError",
    "UnsupportedMediaTypeError",
    "UnprocessableEntityError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    "GatewayTimeoutError",
    "StreamError",
    # models
    "Model",
    "ChatCompletion",
    "ChatChunk",
    "Session",
    "SessionList",
    "Message",
    "MessageList",
    "Job",
    "OCRResult",
    "KnowledgeItem",
    "KnowledgeList",
    "KnowledgeAnswer",
    "ArchiveUnit",
    "ArchiveList",
    "ApiKey",
    "Token",
    "VoiceEvent",
    "ModelInfo",
    "ModelList",
]
