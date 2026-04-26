import json
import re

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)
_MODEL = "gemini-2.5-flash"

_IMAGE_PROMPT = """이 이미지에 있는 분실물/습득물을 분석하고 다음 JSON 형식으로만 응답해줘.

규칙:
- color는 반드시 한국어 표준 색상명 사용 (검정, 흰색, 빨강, 파랑, 노랑, 초록, 갈색, 회색, 베이지, 분홍)
- category는 다음 중 하나만 선택: 지갑, 가방, 휴대폰, 이어폰/에어팟, 열쇠, 카드/신분증, 의류, 우산, 안경, 전자기기/액세서리, 화장품/뷰티, 문구류, 스포츠용품, 기타
- features는 브랜드 로고, 스티커, 흠집, 특이한 장식 등 육안으로 식별 가능한 고유 특징만 작성 (형태 묘사 제외)

{
  "category": "위 목록 중 하나",
  "color": ["표준 색상명"],
  "features": ["고유 특징 1", "고유 특징 2"]
}"""

_TEXT_PROMPT = """다음은 분실물/습득물에 대한 텍스트 설명이야. 이를 분석하고 다음 JSON 형식으로만 응답해줘.

규칙:
- color는 반드시 한국어 표준 색상명 사용 (검정, 흰색, 빨강, 파랑, 노랑, 초록, 갈색, 회색, 베이지, 분홍)
- category는 다음 중 하나만 선택: 지갑, 가방, 휴대폰, 이어폰/에어팟, 열쇠, 카드/신분증, 의류, 우산, 안경, 전자기기/액세서리, 화장품/뷰티, 문구류, 스포츠용품, 기타
- features는 브랜드 로고, 스티커, 흠집, 특이한 장식 등 고유 식별자 중심으로 작성 (형태 묘사 제외)

{
  "category": "위 목록 중 하나",
  "color": ["표준 색상명"],
  "features": ["고유 특징 1", "고유 특징 2"]
}

설명: """


def _parse(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    result = json.loads(cleaned)
    result.setdefault("color", [])
    result.setdefault("features", [])
    return result


def extract_from_text(description: str) -> dict:
    """텍스트 → {"category": str, "color": list[str], "features": list[str]}"""
    response = _client.models.generate_content(
        model=_MODEL,
        contents=_TEXT_PROMPT + description,
    )
    return _parse(response.text)


def extract_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """이미지 bytes → {"category": str, "color": list[str], "features": list[str]}"""
    response = _client.models.generate_content(
        model=_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            _IMAGE_PROMPT,
        ],
    )
    return _parse(response.text)
