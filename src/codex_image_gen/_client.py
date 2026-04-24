from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ._errors import (
    CodexNotFoundError,
    CodexResponseParseError,
    CodexResponsesError,
    ImageDecodeError,
    ImageGenerationNotFoundError,
)
from ._types import GeneratedImage, ImageGenerationResult, PartialGeneratedImage

ImageInput = str | os.PathLike[str] | Mapping[str, str]
MaskInput = str | os.PathLike[str] | Mapping[str, str]

_DEFAULT_MODEL = "gpt-5.5"
_IMAGE_MODEL = "gpt-image-2"
_IMAGE_TOOL_TYPE = "image_generation"
_DEFAULT_INSTRUCTIONS = (
    "Use the image_generation tool when the user asks to draw, create, "
    "generate, or edit an image."
)


def generate_image(
    prompt: str,
    *,
    images: ImageInput | Iterable[ImageInput] | None = None,
    model: str = _DEFAULT_MODEL,
    size: str = "auto",
    quality: str = "auto",
    output_format: str = "png",
    output_compression: int | None = None,
    background: str = "auto",
    action: str = "auto",
    input_image_mask: MaskInput | None = None,
    moderation: str | None = None,
    partial_images: int | None = None,
    reasoning_effort: str | None = None,
    reasoning_summary: str | None = None,
    text_verbosity: str | None = None,
    max_output_tokens: int | None = None,
    instructions: str | None = None,
    timeout: float | None = 300,
    codex_bin: str = "codex",
) -> ImageGenerationResult:
    """Generate an image by sending a Responses API payload to `codex responses`."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    payload = _build_payload(
        prompt=prompt,
        images=images,
        model=model,
        size=size,
        quality=quality,
        output_format=output_format,
        output_compression=output_compression,
        background=background,
        action=action,
        input_image_mask=input_image_mask,
        moderation=moderation,
        partial_images=partial_images,
        reasoning_effort=reasoning_effort,
        reasoning_summary=reasoning_summary,
        text_verbosity=text_verbosity,
        max_output_tokens=max_output_tokens,
        instructions=instructions,
    )
    raw_response = _run_codex_responses(payload, timeout=timeout, codex_bin=codex_bin)
    return _parse_image_generation_response(
        raw_response,
        default_output_format=output_format,
    )


def _build_payload(
    *,
    prompt: str,
    images: ImageInput | Iterable[ImageInput] | None,
    model: str,
    size: str,
    quality: str,
    output_format: str,
    output_compression: int | None,
    background: str,
    action: str,
    input_image_mask: MaskInput | None,
    moderation: str | None,
    partial_images: int | None,
    reasoning_effort: str | None,
    reasoning_summary: str | None,
    text_verbosity: str | None,
    max_output_tokens: int | None,
    instructions: str | None,
) -> dict[str, Any]:
    if background == "transparent":
        raise ValueError("gpt-image-2 does not support transparent backgrounds")

    tool = {
        "type": _IMAGE_TOOL_TYPE,
        "model": _IMAGE_MODEL,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "background": background,
        "action": action,
    }

    if input_image_mask is not None:
        tool["input_image_mask"] = _mask_to_tool_param(input_image_mask)
    if moderation is not None:
        tool["moderation"] = moderation
    if partial_images is not None:
        tool["partial_images"] = partial_images
    if output_compression is not None and output_format in {"jpeg", "webp"}:
        tool["output_compression"] = output_compression

    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions or _DEFAULT_INSTRUCTIONS,
        "input": _build_input(prompt, images),
        "tools": [tool],
        "tool_choice": {"type": _IMAGE_TOOL_TYPE},
        "stream": True,
        "store": False,
    }

    reasoning: dict[str, str] = {}
    if reasoning_effort is not None:
        reasoning["effort"] = reasoning_effort
    if reasoning_summary is not None:
        reasoning["summary"] = reasoning_summary
    if reasoning:
        payload["reasoning"] = reasoning
    if text_verbosity is not None:
        payload["text"] = {"verbosity": text_verbosity}
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    return payload


def _build_input(
    prompt: str,
    images: ImageInput | Iterable[ImageInput] | None,
) -> list[dict[str, Any]]:
    image_inputs = _normalize_images(images)

    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    content.extend(_image_to_content(image) for image in image_inputs)
    return [{"role": "user", "content": content}]


def _normalize_images(
    images: ImageInput | Iterable[ImageInput] | None,
) -> tuple[ImageInput, ...]:
    if images is None:
        return ()
    if isinstance(images, (str, os.PathLike, Mapping)):
        return (images,)
    return tuple(images)


def _image_to_content(image: ImageInput) -> dict[str, str]:
    if isinstance(image, Mapping):
        detail = image.get("detail")
        file_id = image.get("file_id")
        image_url = image.get("image_url")
        path = image.get("path")
        if file_id:
            content = {"type": "input_image", "file_id": file_id}
        elif image_url:
            content = {"type": "input_image", "image_url": image_url}
        elif path:
            content = {
                "type": "input_image",
                "image_url": _path_to_data_url(Path(path)),
            }
        else:
            raise ValueError(
                "image mapping must contain a non-empty 'file_id', "
                "'image_url', or 'path'"
            )
        if detail:
            content["detail"] = detail
        return content

    image_ref = os.fspath(image)
    if image_ref.startswith(("http://", "https://", "data:")):
        return {"type": "input_image", "image_url": image_ref}

    return {"type": "input_image", "image_url": _path_to_data_url(Path(image_ref))}


def _mask_to_tool_param(mask: MaskInput) -> dict[str, str]:
    if isinstance(mask, Mapping):
        file_id = mask.get("file_id")
        image_url = mask.get("image_url")
        if file_id:
            return {"file_id": file_id}
        if image_url:
            return {"image_url": image_url}
        raise ValueError(
            "input_image_mask mapping must contain a non-empty 'file_id' or 'image_url'"
        )

    mask_ref = os.fspath(mask)
    if mask_ref.startswith(("http://", "https://", "data:")):
        return {"image_url": mask_ref}
    return {"image_url": _path_to_data_url(Path(mask_ref))}


def _path_to_data_url(path: Path) -> str:
    data = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _run_codex_responses(
    payload: Mapping[str, Any],
    *,
    timeout: float | None,
    codex_bin: str,
) -> dict[str, Any]:
    stdin = json.dumps(payload, separators=(",", ":"))
    try:
        completed = subprocess.run(
            [codex_bin, "responses"],
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CodexNotFoundError(f"codex executable not found: {codex_bin}") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        message = f"`{codex_bin} responses` exited with code {completed.returncode}"
        if stderr:
            message = f"{message}: {stderr}"
        raise CodexResponsesError(
            message,
            returncode=completed.returncode,
            stderr=stderr,
        )

    return _parse_codex_stdout(completed.stdout)


def _parse_codex_stdout(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return _parse_codex_stream(stdout)

    if not isinstance(parsed, dict):
        raise CodexResponseParseError("codex responses JSON must be an object")
    return parsed


def _parse_codex_stream(stdout: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("event:"):
            continue
        if line.startswith("data:"):
            line = line.removeprefix("data:").strip()
        if line == "[DONE]":
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexResponseParseError(
                "codex responses returned invalid streaming JSON"
            ) from exc
        if not isinstance(event, dict):
            raise CodexResponseParseError(
                "codex responses streaming JSON events must be objects"
            )
        events.append(event)

    if not events:
        raise CodexResponseParseError("codex responses returned no JSON events")

    raw_response: dict[str, Any] = {"output": [], "_events": events}
    for event in events:
        event_type = event.get("type")
        if event_type == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict):
                raw_response["output"].append(item)
        elif event_type == "response.image_generation_call.partial_image":
            raw_response.setdefault("_partial_images", []).append(event)
        elif event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, dict):
                raw_response.update(response)

    return raw_response


def _parse_image_generation_response(
    raw_response: Mapping[str, Any],
    *,
    default_output_format: str = "png",
) -> ImageGenerationResult:
    output = raw_response.get("output")
    if not isinstance(output, list):
        raise ImageGenerationNotFoundError("response did not contain output items")

    generated: list[GeneratedImage] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") != _IMAGE_TOOL_TYPE + "_call":
            continue
        result = item.get("result")
        if not isinstance(result, str) or not result:
            continue
        try:
            data = base64.b64decode(result, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageDecodeError(
                "image_generation_call.result is not valid base64"
            ) from exc

        generated.append(
            GeneratedImage(
                data=data,
                mime_type=_mime_type_from_item(item, default_output_format),
                call_id=_optional_str(item.get("id")),
                revised_prompt=_optional_str(item.get("revised_prompt")),
            )
        )

    if not generated:
        raise ImageGenerationNotFoundError(
            "response did not contain a completed image_generation_call result"
        )

    return ImageGenerationResult(
        images=tuple(generated),
        response_id=_optional_str(raw_response.get("id")),
        raw_response=dict(raw_response),
        partial_images=_parse_partial_images(raw_response, default_output_format),
    )


def _parse_partial_images(
    raw_response: Mapping[str, Any],
    default_output_format: str,
) -> tuple[PartialGeneratedImage, ...]:
    partial_events = raw_response.get("_partial_images", [])
    if not isinstance(partial_events, list):
        return ()

    partials: list[PartialGeneratedImage] = []
    for event in partial_events:
        if not isinstance(event, Mapping):
            continue
        image_base64 = event.get("partial_image_b64")
        if not isinstance(image_base64, str) or not image_base64:
            continue
        try:
            data = base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageDecodeError(
                "partial_image_b64 is not valid base64"
            ) from exc
        partials.append(
            PartialGeneratedImage(
                data=data,
                index=_optional_int(event.get("partial_image_index")),
                mime_type=f"image/{_normalized_output_format(default_output_format)}",
            )
        )
    return tuple(partials)


def _mime_type_from_item(item: Mapping[str, Any], default_output_format: str) -> str:
    output_format = item.get("output_format")
    if not isinstance(output_format, str) or not output_format:
        output_format = default_output_format
    return f"image/{_normalized_output_format(output_format)}"


def _normalized_output_format(output_format: str) -> str:
    return "jpeg" if output_format == "jpg" else output_format


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
