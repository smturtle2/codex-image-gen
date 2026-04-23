from __future__ import annotations


class CodexImageGenError(Exception):
    """Base exception for codex-image-gen errors."""


class CodexNotFoundError(CodexImageGenError):
    """Raised when the Codex CLI executable cannot be found."""


class CodexResponsesError(CodexImageGenError):
    """Raised when `codex responses` exits with a non-zero status."""

    def __init__(self, message: str, *, returncode: int, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class CodexResponseParseError(CodexImageGenError):
    """Raised when `codex responses` returns malformed JSON."""


class ImageGenerationNotFoundError(CodexImageGenError):
    """Raised when the response does not include an image generation result."""


class ImageDecodeError(CodexImageGenError):
    """Raised when an image generation result cannot be base64-decoded."""
