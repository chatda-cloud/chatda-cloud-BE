import json
import re

from google import genai
from google.genai import types


def _get_client() -> genai.Client:
    """호출 시점에 클라이언트 생성 (모듈 로드 시 ASCII 에러 방지)."""
    from app.config import get_settings
    return genai.Client(api_key=get_settings().GEMINI_API_KEY)


_MODEL = "gemini-2.5-flash"

_IMAGE_PROMPT_BASE = """이 이미지에 있는 분실물/습득물을 분석하고 다음 JSON 형식으로만 응답해줘.

규칙:
- category는 반드시 다음 목록 중 하나만 선택: 지갑, 가방, 휴대폰, 이어폰/에어팟, 열쇠, 카드/신분증, 의류, 우산, 안경, 전자기기/액세서리, 화장품/뷰티, 문구류, 스포츠용품, 기타
- color는 반드시 한국어 표준 색상명 사용 (검정, 흰색, 빨강, 파랑, 노랑, 초록, 갈색, 회색, 베이지, 분홍)
- features는 브랜드 로고, 스티커, 흠집, 특이한 장식 등 육안으로 식별 가능한 고유 특징만 작성 (형태 묘사 제외)
- 추가 정보가 있다면 이미지 판단의 보조 힌트로만 활용하고, 최종 판단은 이미지 기준으로 해줘

{
  "category": "위 목록 중 하나",
  "color": ["표준 색상명"],
  "features": ["고유 특징 1", "고유 특징 2"]
}"""

_TEXT_PROMPT = """다음은 분실물/습득물 정보야. 이를 분석하고 다음 JSON 형식으로만 응답해줘.

규칙:
- category는 다음 중 하나만 선택: 지갑, 가방, 휴대폰, 이어폰/에어팟, 열쇠, 카드/신분증, 의류, 우산, 안경, 전자기기/액세서리, 화장품/뷰티, 문구류, 스포츠용품, 기타
- color는 반드시 한국어 표준 색상명 사용 (검정, 흰색, 빨강, 파랑, 노랑, 초록, 갈색, 회색, 베이지, 분홍)
- features는 브랜드 로고, 스티커, 흠집, 특이한 장식 등 고유 식별자 중심으로 작성 (형태 묘사 제외)
- 물건 이름이 명확하게 주어진 경우 category 판단의 최우선 기준으로 삼을 것

{{
  "category": "위 목록 중 하나",
  "color": ["표준 색상명"],
  "features": ["고유 특징 1", "고유 특징 2"]
}}

물건 이름: {item_name}
상세 설명: {raw_text}
"""


def _build_image_prompt(
    rekognition_labels: list[str] | None = None,
    user_text: str | None = None,
) -> str:
    hint_lines = []
    if rekognition_labels:
        hint_lines.append(f"- AI 객체 탐지 결과 (힌트): {', '.join(rekognition_labels)}")
    if user_text:
        hint_lines.append(f"- 사용자 설명: {user_text}")

    if not hint_lines:
        return _IMAGE_PROMPT_BASE

    return _IMAGE_PROMPT_BASE + "\n\n추가 정보:\n" + "\n".join(hint_lines)


def _parse(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    result = json.loads(cleaned)
    result.setdefault("color", [])
    result.setdefault("features", [])
    return result


def extract_from_text(item_name: str, raw_text: str = "") -> dict:
    prompt = _TEXT_PROMPT.format(
        item_name=item_name,
        raw_text=raw_text or "없음",
    )
    from app.config import get_settings
    with genai.Client(api_key=get_settings().GEMINI_API_KEY) as client:
        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
        )
    return _parse(response.text)


def extract_from_image(
    image_bytes: bytes,
    rekognition_labels: list[str] | None = None,
    user_text: str | None = None,
    mime_type: str = "image/jpeg",
) -> dict:
    prompt = _build_image_prompt(rekognition_labels, user_text)
    from app.config import get_settings
    with genai.Client(api_key=get_settings().GEMINI_API_KEY) as client:
        response = client.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
        )
    return _parse(response.text)