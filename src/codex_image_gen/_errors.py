from __future__ import annotations


class CodexImageGenError(Exception):
    """Base exception for codex-image-gen errors."""


class OAuthResponsesError(CodexImageGenError):
    """Raised when the Codex OAuth Responses bridge returns an error."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: str = "",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class CodexResponseParseError(CodexImageGenError):
    """Raised when the Responses bridge returns malformed JSON."""


class ImageGenerationNotFoundError(CodexImageGenError):
    """Raised when the response does not include an image generation result."""


class ImageDecodeError(CodexImageGenError):
    """Raised when an image generation result cannot be base64-decoded."""
