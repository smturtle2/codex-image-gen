from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._errors import (
    CodexResponseParseError,
    ImageDecodeError,
    ImageGenerationNotFoundError,
    OAuthResponsesError,
)
from ._types import GeneratedImage, ImageGenerationResult, PartialGeneratedImage

ImageInput = str | os.PathLike[str] | Mapping[str, str]
MaskInput = str | os.PathLike[str] | Mapping[str, str]

_DEFAULT_MODEL = "gpt-5.5"
_IMAGE_MODEL = "gpt-image-2"
_IMAGE_TOOL_TYPE = "image_generation"
_DEFAULT_OAUTH_BASE_URL = "https://chatgpt.com/backend-api/codex"
_DEFAULT_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
_DEFAULT_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
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
    output_format: str = "png",
    output_compression: int | None = None,
    background: str = "auto",
    input_image_mask: MaskInput | None = None,
    moderation: str | None = None,
    partial_images: int | None = None,
    reasoning_effort: str | None = None,
    reasoning_summary: str | None = None,
    text_verbosity: str | None = None,
    instructions: str | None = None,
    timeout: float | None = 300,
    oauth_base_url: str = _DEFAULT_OAUTH_BASE_URL,
    auth_file: str | os.PathLike[str] | None = None,
) -> ImageGenerationResult:
    """Generate an image through the Codex OAuth Responses bridge."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    payload = _build_payload(
        prompt=prompt,
        images=images,
        model=model,
        size=size,
        output_format=output_format,
        output_compression=output_compression,
        background=background,
        input_image_mask=input_image_mask,
        moderation=moderation,
        partial_images=partial_images,
        reasoning_effort=reasoning_effort,
        reasoning_summary=reasoning_summary,
        text_verbosity=text_verbosity,
        instructions=instructions,
    )
    raw_response = _run_oauth_responses(
        payload,
        timeout=timeout,
        base_url=oauth_base_url,
        auth_file=auth_file,
    )
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
    output_format: str,
    output_compression: int | None,
    background: str,
    input_image_mask: MaskInput | None,
    moderation: str | None,
    partial_images: int | None,
    reasoning_effort: str | None,
    reasoning_summary: str | None,
    text_verbosity: str | None,
    instructions: str | None,
) -> dict[str, Any]:
    if background == "transparent":
        raise ValueError("gpt-image-2 does not support transparent backgrounds")

    tool = {
        "type": _IMAGE_TOOL_TYPE,
        "model": _IMAGE_MODEL,
        "size": size,
        "output_format": output_format,
        "background": background,
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


def _run_oauth_responses(
    payload: Mapping[str, Any],
    *,
    timeout: float | None,
    base_url: str,
    auth_file: str | os.PathLike[str] | None,
) -> dict[str, Any]:
    headers = _oauth_headers(auth_file)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "text/event-stream"

    endpoint = f"{base_url.rstrip('/')}/responses"
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            stdout = response.read().decode(charset)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        message = f"Codex OAuth Responses bridge returned HTTP {exc.code}"
        if body_text:
            message = f"{message}: {body_text}"
        raise OAuthResponsesError(message, status=exc.code, body=body_text) from exc
    except urllib.error.URLError as exc:
        raise OAuthResponsesError(
            f"Codex OAuth Responses bridge request failed: {exc.reason}"
        ) from exc

    return _parse_responses_stdout(stdout)


def _oauth_headers(auth_file: str | os.PathLike[str] | None) -> dict[str, str]:
    auth = _load_auth(auth_file)
    tokens = auth.get("tokens")
    if not isinstance(tokens, Mapping):
        raise OAuthResponsesError("Codex auth file does not contain OAuth tokens")

    access_token = _optional_str(tokens.get("access_token"))
    refresh_token = _optional_str(tokens.get("refresh_token"))
    id_token = _optional_str(tokens.get("id_token"))
    account_id = _optional_str(tokens.get("account_id")) or _account_id_from_id_token(
        id_token
    )

    last_refresh = _optional_str(auth.get("last_refresh"))
    if refresh_token and _should_refresh(access_token, last_refresh):
        refreshed = _refresh_tokens(refresh_token)
        tokens = {
            "id_token": refreshed.get("id_token") or id_token,
            "access_token": refreshed["access_token"],
            "refresh_token": refreshed.get("refresh_token") or refresh_token,
            "account_id": _account_id_from_id_token(refreshed.get("id_token"))
            or account_id,
        }
        auth["tokens"] = tokens
        auth["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        _write_auth(auth_file, auth)
        access_token = _optional_str(tokens.get("access_token"))
        account_id = _optional_str(tokens.get("account_id"))

    if not access_token:
        raise OAuthResponsesError(
            "Codex OAuth access token not found; run `codex login`"
        )
    if not account_id:
        raise OAuthResponsesError("Codex OAuth account id not found; run `codex login`")

    return {
        "Authorization": f"Bearer {access_token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
    }


def _load_auth(auth_file: str | os.PathLike[str] | None) -> dict[str, Any]:
    path = _auth_file_path(auth_file)
    try:
        data = json.loads(path.read_text("utf-8"))
    except FileNotFoundError as exc:
        raise OAuthResponsesError(f"Codex auth file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OAuthResponsesError(f"Codex auth file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise OAuthResponsesError(f"Codex auth file must contain a JSON object: {path}")
    return data


def _write_auth(
    auth_file: str | os.PathLike[str] | None,
    auth: Mapping[str, Any],
) -> None:
    path = _auth_file_path(auth_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(auth, indent=2), encoding="utf-8")
    path.chmod(0o600)


def _auth_file_path(auth_file: str | os.PathLike[str] | None) -> Path:
    if auth_file is not None:
        return Path(auth_file).expanduser()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _should_refresh(access_token: str | None, last_refresh: str | None) -> bool:
    if not access_token:
        return True
    claims = _jwt_claims(access_token)
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp <= time.time() + 300:
        return True
    if last_refresh is None:
        return False
    value = last_refresh.replace("Z", "+00:00")
    try:
        refreshed_at = datetime.fromisoformat(value)
    except ValueError:
        return True
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=UTC)
    return refreshed_at.timestamp() <= time.time() - 55 * 60


def _refresh_tokens(refresh_token: str) -> dict[str, str]:
    body = json.dumps(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _DEFAULT_OAUTH_CLIENT_ID,
            "scope": "openid profile email offline_access",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        _DEFAULT_OAUTH_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            refreshed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise OAuthResponsesError(
            f"Codex OAuth token refresh returned HTTP {exc.code}: {body_text}",
            status=exc.code,
            body=body_text,
        ) from exc
    except urllib.error.URLError as exc:
        raise OAuthResponsesError(
            f"Codex OAuth token refresh failed: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OAuthResponsesError(
            "Codex OAuth token refresh returned invalid JSON"
        ) from exc

    if not isinstance(refreshed, dict) or not isinstance(
        refreshed.get("access_token"), str
    ):
        raise OAuthResponsesError(
            "Codex OAuth token refresh did not return access_token"
        )
    return refreshed


def _account_id_from_id_token(id_token: str | None) -> str | None:
    claims = _jwt_claims(id_token)
    auth_claim = claims.get("https://api.openai.com/auth")
    if isinstance(auth_claim, Mapping):
        return _optional_str(auth_claim.get("chatgpt_account_id"))
    return None


def _jwt_claims(token: str | None) -> dict[str, Any]:
    if not token or "." not in token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        claims = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _parse_responses_stdout(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return _parse_responses_stream(stdout)

    if not isinstance(parsed, dict):
        raise CodexResponseParseError("Responses bridge JSON must be an object")
    return parsed


def _parse_responses_stream(stdout: str) -> dict[str, Any]:
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
                "Responses bridge returned invalid streaming JSON"
            ) from exc
        if not isinstance(event, dict):
            raise CodexResponseParseError(
                "Responses bridge streaming JSON events must be objects"
            )
        events.append(event)

    if not events:
        raise CodexResponseParseError("Responses bridge returned no JSON events")

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
                output = raw_response["output"]
                partial_images = raw_response.get("_partial_images")
                raw_response.update(response)
                if not raw_response.get("output") and output:
                    raw_response["output"] = output
                if partial_images:
                    raw_response["_partial_images"] = partial_images

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
