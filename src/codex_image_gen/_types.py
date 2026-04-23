from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeneratedImage:
    """A decoded image returned by an image generation tool call."""

    data: bytes
    mime_type: str
    call_id: str | None = None
    revised_prompt: str | None = None


@dataclass(frozen=True)
class PartialGeneratedImage:
    """A partial image streamed before the final image is ready."""

    data: bytes
    index: int | None
    mime_type: str


@dataclass(frozen=True)
class ImageGenerationResult:
    """Images plus metadata from the raw Responses API result."""

    images: tuple[GeneratedImage, ...]
    response_id: str | None
    raw_response: dict[str, Any]
    partial_images: tuple[PartialGeneratedImage, ...] = ()
