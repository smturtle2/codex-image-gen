# codex-image-gen

Python helpers for generating images through `codex responses`.

This package uses the Codex CLI as the transport. It sends a raw Responses API
JSON payload to `codex responses`, which means authentication is handled by your
existing Codex login rather than by an `OPENAI_API_KEY`.

## Install

```bash
uv add codex-image-gen
```

For local development:

```bash
uv sync --dev
```

## Usage

```python
from pathlib import Path

from codex_image_gen import generate_image

result = generate_image(
    "Draw a small lighthouse on a cliff at sunrise",
    size="1024x1024",
    quality="medium",
)

image = result.images[0]
Path("lighthouse.png").write_bytes(image.data)
```

Reference images can be passed as local paths, `http(s)` URLs, `data:` URLs, or
file IDs. Mapping inputs also support the Responses `input_image.detail` field:

```python
result = generate_image(
    "Edit the reference image into a watercolor postcard",
    images=["reference.png", {"file_id": "file_123", "detail": "high"}],
    action="edit",
)
```

All Responses image generation tool options are exposed:

```python
result = generate_image(
    "Edit the logo area and keep the product shape",
    images=["product.png"],
    input_image_mask="mask.png",
    moderation="low",
    partial_images=2,
    size="2048x2048",
    quality="high",
    output_format="webp",
    output_compression=70,
    background="opaque",
    action="edit",
)

for partial in result.partial_images:
    Path(f"partial-{partial.index}.webp").write_bytes(partial.data)
```

## Notes

- `codex` must be installed and logged in.
- The default Responses model is `gpt-5.4`.
- The image generation tool is fixed to `gpt-image-2`.
- `codex responses` requires `store=false`, so prior response/item references
  are not exposed by this library. Use image bytes or file IDs as inputs for
  follow-up edits.
- `gpt-image-2` does not support `background="transparent"` or
  `input_fidelity`; the library does not expose `input_fidelity` and rejects
  transparent backgrounds before calling Codex.
- `partial_images` are collected and returned after `codex responses` exits.
  This function does not expose a live streaming callback.
- The package returns image bytes and metadata; it does not write files.
- Tests mock `codex responses` and do not make live API calls.
