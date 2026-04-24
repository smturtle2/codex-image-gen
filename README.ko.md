<div align="center">
  <img src="./codex-image-gen-hero.png" alt="codex-image-gen 히어로 이미지" width="900">

  <h1>codex-image-gen</h1>
  <p><strong>Codex responses를 통해 Python에서 이미지를 생성합니다</strong></p>

  <p>
    <a href="./README.md">English</a> ·
    <a href="./README.ko.md">한국어</a>
  </p>

  <p>
    <a href="https://github.com/smturtle2/codex-image-gen/actions/workflows/workflow.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/smturtle2/codex-image-gen/workflow.yml?branch=main&label=tests"></a>
    <a href="https://github.com/smturtle2/codex-image-gen/releases/tag/v0.1.1"><img alt="Release" src="https://img.shields.io/github/v/release/smturtle2/codex-image-gen?label=release"></a>
    <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/smturtle2/codex-image-gen"></a>
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
    <img alt="Model" src="https://img.shields.io/badge/gpt--image--2-enabled-6f42c1">
    <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-zero-2ea44f">
  </p>
</div>

---

`codex-image-gen`은 Codex CLI의 `responses` 명령과 Responses API
`image_generation` 도구를 통해 고품질 이미지를 생성하는 작고 의존성 없는
Python 라이브러리입니다.

기존 Codex 로그인 인증을 그대로 사용하며, `codex responses`에 raw Responses
payload를 전달한 뒤 디코딩된 이미지 bytes와 메타데이터를 Python dataclass로
반환합니다.

## Demo

<p align="center">
  <img src="./codex-image-gen-demo.webp" alt="생성된 앱 아이콘 데모" width="420">
</p>

<p align="center">
  <em><code>codex-image-gen</code> + <code>gpt-image-2</code>로 생성한 이미지입니다.</em>
</p>

## Quick Start

<p align="center">
  <img src="./codex-image-gen-quickstart.png" alt="codex-image-gen quick start 코드 카드" width="760">
</p>

```bash
uv add codex-image-gen

# 또는
pip install codex-image-gen
```

```python
from pathlib import Path

from codex_image_gen import generate_image

result = generate_image(
    "A serene mountain landscape with a lake and pine trees, sunset light",
    size="1024x1024",
    quality="low",
    output_format="png",
)

image = result.images[0]
Path("mountain.png").write_bytes(image.data)
print("saved:", image.mime_type, len(image.data), "bytes")
```

이것으로 끝입니다. 이미지는 로컬 파일로 저장됩니다.

## Features

<p align="center">
  <img src="./codex-image-gen-workflow.png" alt="codex-image-gen 워크플로 다이어그램" width="760">
</p>

| | |
| --- | --- |
| **고품질 이미지**<br>Codex responses를 통해 `gpt-image-2`를 사용합니다. | **다양한 입력 타입**<br>로컬 경로, URL, data URL, file ID, `detail` 매핑을 사용할 수 있습니다. |
| **안정적인 예외 처리**<br>Codex 실패, 잘못된 JSON, 누락된 이미지 결과, 잘못된 base64를 명확한 예외로 감쌉니다. | **라이브 검증된 파라미터 표면**<br>현재 Codex bridge에서 실제 동작한 gpt-image-2 옵션만 전달합니다. |
| **타입 있는 결과**<br>이미지 bytes, MIME type, response ID, call ID, revised prompt, partial image를 frozen dataclass로 반환합니다. | **무거운 의존성 없음**<br>런타임은 Python 표준 라이브러리와 Codex CLI만 사용합니다. |

## API Highlights

```python
generate_image(
    prompt: str,
    *,
    images=None,
    model="gpt-5.5",
    size="auto",
    quality="auto",
    output_format="png",
    output_compression=None,
    background="auto",
    action="auto",
    input_image_mask=None,
    moderation=None,
    partial_images=None,
    reasoning_effort=None,
    reasoning_summary=None,
    text_verbosity=None,
    max_output_tokens=None,
    instructions=None,
    timeout=300,
    codex_bin="codex",
)
```

- 단순하고 조합하기 쉬운 함수 API입니다.
- 이미지, 메타데이터, raw response, optional partial image를 포함한 풍부한 결과 객체를 제공합니다.
- 참조 이미지는 로컬 파일, 원격 URL, `data:` URL, file ID로 전달할 수 있습니다.
- mask edit는 `input_image_mask`를 사용합니다. mask는 로컬 경로, URL,
  `data:` URL, file ID로 전달할 수 있으며, 편집할 이미지와 같은 크기 및
  포맷이어야 하고 50MB 미만, alpha channel 포함이어야 합니다.
- reasoning effort, reasoning summary, text verbosity, max output tokens,
  timeout, moderation, output format, compression, custom instructions를 일급
  옵션으로 제공합니다.

## Examples

### 참조 이미지로 편집

```python
result = generate_image(
    "Edit the reference image into a watercolor postcard",
    images=[
        "reference.png",
        {"file_id": "file_123", "detail": "high"},
    ],
    action="edit",
    output_format="webp",
    output_compression=75,
)

Path("postcard.webp").write_bytes(result.images[0].data)
```

### 마스크 편집

<p align="center">
  <img src="./codex-image-gen-masked-edit.png" alt="codex-image-gen 마스크 편집 워크플로" width="720">
</p>

위 이미지는 워크플로를 설명하는 그림입니다. 실제 마스크 편집에는 편집할
이미지와 같은 크기 및 포맷의 alpha-channel mask를 사용하세요.

```python
result = generate_image(
    "Replace only the masked logo area with a white star",
    images=["product.png"],
    input_image_mask="mask_alpha.png",
    action="edit",
    background="opaque",
)

Path("edited.png").write_bytes(result.images[0].data)
```

### Partial Images

```python
result = generate_image(
    "Create a polished app icon of a glass bottle",
    partial_images=2,
)

for partial in result.partial_images:
    Path(f"partial-{partial.index}.png").write_bytes(partial.data)
```

partial image는 `codex responses`가 종료된 뒤 결과 객체에 수집됩니다. 이 함수는
실시간 streaming callback을 제공하지 않습니다.

### Reasoning Settings

```python
result = generate_image(
    "Create a detailed concept sheet for a modular desk lamp",
    reasoning_effort="high",
    reasoning_summary="auto",
    text_verbosity="low",
    max_output_tokens=4096,
)
```

`reasoning_effort`는 `none`, `minimal`, `low`, `medium`, `high`, `xhigh`를
지원합니다. `text_verbosity`는 `low`, `medium`, `high`를 지원합니다.

## Compatibility

이 라이브러리는 현재 `codex responses` bridge에서 라이브 테스트로 동작을 확인한
파라미터만 노출합니다.

- 기본 mainline Responses model은 `gpt-5.5`입니다.
- 이미지 생성 도구에는 항상 `model="gpt-image-2"`를 보냅니다.
- `input_image_mask`는 Responses `image_generation` tool에 문서화되어 있고
  Codex bridge에서 라이브 테스트를 통과했기 때문에 노출합니다. 이 라이브러리는
  mask를 그대로 전달하며, 필요한 alpha channel을 자동 생성하지는 않습니다.
- `background="transparent"`는 Codex 호출 전에 거부합니다.
- `input_fidelity`는 `gpt-image-2`가 거부하므로 노출하지 않습니다.
- `previous_response_id`와 이전 `image_generation_call` item 참조는 노출하지
  않습니다. Codex가 `store=false`를 요구해 이전 item이 저장되지 않기 때문입니다.
  후속 편집에는 이미지 bytes, 로컬 파일, URL, file ID를 사용하세요.

## Development

```bash
git clone https://github.com/smturtle2/codex-image-gen.git
cd codex-image-gen
uv sync --dev
uv run ruff check .
uv run pytest
uv build
```

## Project Links

| Link | Description |
| --- | --- |
| [Documentation](./README.md) | 영어 문서 |
| [Examples](#examples) | 사용 예시 |
| [Contributing](#development) | 로컬 개발 흐름 |
| [Issues](https://github.com/smturtle2/codex-image-gen/issues) | 버그 제보와 기능 요청 |
| [Discussions](https://github.com/smturtle2/codex-image-gen/discussions) | 질문과 논의 |
| [PyPI](https://pypi.org/project/codex-image-gen/) | 배포된 Python 패키지 |
| [Release v0.1.1](https://github.com/smturtle2/codex-image-gen/releases/tag/v0.1.1) | wheel 및 sdist 아티팩트 |

## Release

`v0.1.1`은 PyPI와 wheel/sdist가 포함된 GitHub Release로 제공됩니다.

PyPI에서 설치하세요:

```bash
uv add codex-image-gen

# 또는
pip install codex-image-gen
```

## License

MIT
