import base64
import inspect
import json
import urllib.request

import pytest

import codex_image_gen
import codex_image_gen._client as client


def _response_with_image(data=b"image-bytes"):
    return {
        "id": "resp_123",
        "output": [
            {
                "type": "image_generation_call",
                "id": "ig_123",
                "result": base64.b64encode(data).decode("ascii"),
                "revised_prompt": "a revised prompt",
            }
        ],
    }


def _stream_with_image(data=b"image-bytes"):
    events = [
        {"type": "response.created", "response": {}},
        {
            "type": "response.image_generation_call.partial_image",
            "partial_image_index": 0,
            "partial_image_b64": base64.b64encode(b"partial-image").decode("ascii"),
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "image_generation_call",
                "id": "ig_stream",
                "result": base64.b64encode(data).decode("ascii"),
                "revised_prompt": "a stream revised prompt",
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp_stream",
                "output": [],
                "usage": {"total_tokens": 10},
            },
        },
    ]
    stdout = "\n".join(json.dumps(event) for event in events) + "\n"
    return events, client._parse_responses_stdout(stdout)


def _mock_oauth(monkeypatch, raw_response):
    calls = []

    def fake_run(payload, **kwargs):
        calls.append((payload, kwargs))
        return raw_response

    monkeypatch.setattr(client, "_run_oauth_responses", fake_run)
    return calls


def _payload_from_call(calls):
    assert len(calls) == 1
    payload, _ = calls[0]
    return payload


def _user_content(payload):
    assert payload["input"][0]["role"] == "user"
    return payload["input"][0]["content"]


def _image_generation_tool(payload):
    tools = payload["tools"]
    matches = [tool for tool in tools if tool["type"] == "image_generation"]
    assert len(matches) == 1
    return matches[0]


def _assert_codex_payload_defaults(payload):
    assert isinstance(payload["instructions"], str)
    assert payload["stream"] is True
    assert payload["store"] is False
    assert payload["tool_choice"] == {"type": "image_generation"}


def test_text_only_generation_builds_codex_responses_call_and_decodes_image(
    monkeypatch,
):
    raw_response = _response_with_image(b"\x89PNG\r\nimage-data")
    calls = _mock_oauth(monkeypatch, raw_response)

    result = codex_image_gen.generate_image("draw a red cube")

    _, kwargs = calls[0]
    assert kwargs["timeout"] == 300
    assert kwargs["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert kwargs["auth_file"] is None

    payload = _payload_from_call(calls)
    _assert_codex_payload_defaults(payload)
    assert payload["model"] == "gpt-5.5"
    assert _user_content(payload) == [
        {"type": "input_text", "text": "draw a red cube"}
    ]
    assert _image_generation_tool(payload) == {
        "type": "image_generation",
        "model": "gpt-image-2",
        "size": "auto",
        "output_format": "png",
        "background": "auto",
    }

    assert result.response_id == "resp_123"
    assert result.raw_response == raw_response
    assert isinstance(result.images, tuple)
    assert len(result.images) == 1
    generated = result.images[0]
    assert generated.data == b"\x89PNG\r\nimage-data"
    assert generated.mime_type == "image/png"
    assert generated.call_id == "ig_123"
    assert generated.revised_prompt == "a revised prompt"


def test_streaming_ndjson_response_decodes_image(monkeypatch):
    events, raw_response = _stream_with_image(b"stream-image-data")
    _mock_oauth(monkeypatch, raw_response)

    result = codex_image_gen.generate_image("draw a blue circle")

    assert result.response_id == "resp_stream"
    assert result.raw_response["_events"] == events
    assert result.raw_response["usage"] == {"total_tokens": 10}
    assert result.images[0].data == b"stream-image-data"
    assert result.images[0].call_id == "ig_stream"
    assert result.images[0].revised_prompt == "a stream revised prompt"
    assert len(result.partial_images) == 1
    assert result.partial_images[0].data == b"partial-image"
    assert result.partial_images[0].index == 0
    assert result.partial_images[0].mime_type == "image/png"


def test_generate_image_signature_excludes_removed_image_tool_parameters():
    signature = inspect.signature(codex_image_gen.generate_image)

    assert "image_model" not in signature.parameters
    assert "input_fidelity" not in signature.parameters
    assert "previous_response_id" not in signature.parameters
    assert "image_generation_call_ids" not in signature.parameters
    assert "backend" not in signature.parameters
    assert "codex_bin" not in signature.parameters
    assert "max_output_tokens" not in signature.parameters
    assert "quality" not in signature.parameters
    assert "action" not in signature.parameters


def test_reasoning_and_text_options_are_forwarded(monkeypatch):
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    codex_image_gen.generate_image(
        "draw carefully",
        reasoning_effort="high",
        reasoning_summary="auto",
        text_verbosity="low",
    )

    payload = _payload_from_call(calls)
    assert payload["reasoning"] == {"effort": "high", "summary": "auto"}
    assert payload["text"] == {"verbosity": "low"}


def test_all_gpt_image_2_tool_parameters_are_forwarded(monkeypatch, tmp_path):
    mask_path = tmp_path / "mask.png"
    mask_path.write_bytes(b"mask-bytes")
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    codex_image_gen.generate_image(
        "edit this product photo",
        images=["data:image/png;base64,AAAA"],
        model="gpt-custom",
        size="1024x1792",
        output_format="webp",
        output_compression=73,
        background="opaque",
        input_image_mask=mask_path,
        moderation="low",
        partial_images=2,
        instructions="Always use the image tool.",
    )

    payload = _payload_from_call(calls)
    assert payload["instructions"] == "Always use the image tool."
    assert _image_generation_tool(payload) == {
        "type": "image_generation",
        "model": "gpt-image-2",
        "size": "1024x1792",
        "output_format": "webp",
        "background": "opaque",
        "input_image_mask": {
            "image_url": (
                "data:image/png;base64,"
                + base64.b64encode(b"mask-bytes").decode("ascii")
            ),
        },
        "moderation": "low",
        "partial_images": 2,
        "output_compression": 73,
    }


def test_transparent_background_raises_for_gpt_image_2(monkeypatch):
    calls = _mock_oauth(monkeypatch, _response_with_image())

    with pytest.raises(ValueError, match="gpt-image-2.*transparent"):
        codex_image_gen.generate_image("make a logo", background="transparent")

    assert calls == []


def test_flexible_size_strings_are_forwarded(monkeypatch):
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    codex_image_gen.generate_image("wide poster", size="2048x1024")

    tool = _image_generation_tool(_payload_from_call(calls))
    assert tool["model"] == "gpt-image-2"
    assert tool["size"] == "2048x1024"


def test_input_image_mask_accepts_file_id_and_image_url(monkeypatch):
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    codex_image_gen.generate_image(
        "mask by file",
        input_image_mask={"file_id": "file_mask"},
    )
    assert _image_generation_tool(_payload_from_call(calls))["input_image_mask"] == {
        "file_id": "file_mask"
    }

    calls.clear()
    codex_image_gen.generate_image(
        "mask by data URL",
        input_image_mask={"image_url": "data:image/png;base64,BBBB"},
    )
    assert _image_generation_tool(_payload_from_call(calls))["input_image_mask"] == {
        "image_url": "data:image/png;base64,BBBB"
    }


def test_local_image_path_becomes_data_url_with_inferred_mime_type(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "reference.jpg"
    image_path.write_bytes(b"local-image-bytes")
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    codex_image_gen.generate_image("use this reference", images=[image_path])

    content = _user_content(_payload_from_call(calls))
    assert content == [
        {"type": "input_text", "text": "use this reference"},
        {
            "type": "input_image",
            "image_url": (
                "data:image/jpeg;base64,"
                + base64.b64encode(b"local-image-bytes").decode("ascii")
            ),
        },
    ]


def test_url_data_url_and_file_id_images_are_accepted_in_content(monkeypatch):
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)
    data_url = "data:image/webp;base64,AAAA"

    codex_image_gen.generate_image(
        "combine references",
        images=[
            "https://example.test/reference.png",
            data_url,
            {"file_id": "file_abc123", "detail": "high"},
            {"image_url": "https://example.test/second.png", "detail": "low"},
        ],
    )

    content = _user_content(_payload_from_call(calls))
    assert content == [
        {"type": "input_text", "text": "combine references"},
        {
            "type": "input_image",
            "image_url": "https://example.test/reference.png",
        },
        {"type": "input_image", "image_url": data_url},
        {"type": "input_image", "file_id": "file_abc123", "detail": "high"},
        {
            "type": "input_image",
            "image_url": "https://example.test/second.png",
            "detail": "low",
        },
    ]


def test_image_mapping_path_is_accepted(monkeypatch, tmp_path):
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"path-image")
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    codex_image_gen.generate_image(
        "use mapped image path",
        images={"path": str(image_path), "detail": "auto"},
    )

    payload = _payload_from_call(calls)
    assert payload["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "use mapped image path"},
                {
                    "type": "input_image",
                    "image_url": (
                        "data:image/png;base64,"
                        + base64.b64encode(b"path-image").decode("ascii")
                    ),
                    "detail": "auto",
                },
            ],
        }
    ]


@pytest.mark.parametrize(
    ("output_format", "expected_mime_type", "should_include_compression"),
    [
        ("png", "image/png", False),
        ("jpeg", "image/jpeg", True),
        ("webp", "image/webp", True),
    ],
)
def test_output_compression_only_included_for_jpeg_and_webp(
    monkeypatch,
    output_format,
    expected_mime_type,
    should_include_compression,
):
    raw_response = _response_with_image()
    calls = _mock_oauth(monkeypatch, raw_response)

    result = codex_image_gen.generate_image(
        "compress if supported",
        output_format=output_format,
        output_compression=82,
    )

    tool = _image_generation_tool(_payload_from_call(calls))
    assert tool["model"] == "gpt-image-2"
    assert tool["output_format"] == output_format
    assert ("output_compression" in tool) is should_include_compression
    if should_include_compression:
        assert tool["output_compression"] == 82
    assert result.images[0].mime_type == expected_mime_type


def test_oauth_backend_error_is_propagated(monkeypatch):
    calls = []

    def fake_run(payload, **kwargs):
        calls.append((payload, kwargs))
        raise codex_image_gen.OAuthResponsesError("no auth", status=401)

    monkeypatch.setattr(client, "_run_oauth_responses", fake_run)

    with pytest.raises(codex_image_gen.OAuthResponsesError) as exc_info:
        codex_image_gen.generate_image("hello")

    assert len(calls) == 1
    assert "no auth" in str(exc_info.value)


def test_run_oauth_responses_posts_to_codex_backend(monkeypatch, tmp_path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "access-token",
                    "account_id": "account-id",
                    "refresh_token": "refresh-token",
                }
            }
        ),
        encoding="utf-8",
    )
    raw_response = _response_with_image()
    calls = []

    class FakeHeaders:
        def get_content_charset(self):
            return "utf-8"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(raw_response).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = client._run_oauth_responses(
        {"model": "gpt-5.5", "stream": True},
        timeout=123,
        base_url="https://chatgpt.com/backend-api/codex",
        auth_file=auth_file,
    )

    request, timeout = calls[0]
    assert result == raw_response
    assert timeout == 123
    assert request.full_url == "https://chatgpt.com/backend-api/codex/responses"
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == "Bearer access-token"
    assert request.headers["Chatgpt-account-id"] == "account-id"
    assert request.headers["Openai-beta"] == "responses=experimental"
    assert json.loads(request.data.decode("utf-8")) == {
        "model": "gpt-5.5",
        "stream": True,
    }


def test_malformed_json_becomes_codex_response_parse_error(monkeypatch):
    with pytest.raises(codex_image_gen.CodexResponseParseError):
        client._parse_responses_stdout("{not valid json")


def test_missing_image_generation_call_becomes_image_generation_not_found_error(
    monkeypatch,
):
    _mock_oauth(monkeypatch, {"id": "resp_123", "output": []})

    with pytest.raises(codex_image_gen.ImageGenerationNotFoundError):
        codex_image_gen.generate_image("hello")


def test_bad_base64_becomes_image_decode_error(monkeypatch):
    raw = {
        "id": "resp_123",
        "output": [
            {
                "type": "image_generation_call",
                "id": "ig_123",
                "result": "not base64!",
            }
        ],
    }
    _mock_oauth(monkeypatch, raw)

    with pytest.raises(codex_image_gen.ImageDecodeError):
        codex_image_gen.generate_image("hello")


def test_bad_partial_image_base64_becomes_image_decode_error(monkeypatch):
    events = [
        {
            "type": "response.image_generation_call.partial_image",
            "partial_image_index": 0,
            "partial_image_b64": "not base64!",
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "image_generation_call",
                "id": "ig_123",
                "result": base64.b64encode(b"final").decode("ascii"),
            },
        },
    ]
    raw_response = client._parse_responses_stdout(
        "\n".join(json.dumps(event) for event in events)
    )
    _mock_oauth(
        monkeypatch,
        raw_response,
    )

    with pytest.raises(codex_image_gen.ImageDecodeError):
        codex_image_gen.generate_image("hello", partial_images=1)
