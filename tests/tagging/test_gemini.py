"""
gemini.py 단위 테스트.

검증 항목:
  1. _build_image_prompt — 힌트 유무에 따른 프롬프트 생성
  2. _parse — JSON 파싱 및 누락 필드 기본값
  3. extract_from_image — Rekognition 라벨·사용자 텍스트가 프롬프트에 포함되는지
  4. extract_from_text — 텍스트 전용 경로
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ── 환경변수 없이도 config가 로드되도록 더미 설정 ──────────────────────────
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

from app.tagging import gemini


# ─────────────────────────────────────────────────────────────────────────────
# _build_image_prompt
# ─────────────────────────────────────────────────────────────────────────────
class TestBuildImagePrompt:
    def test_no_hints_omits_additional_section(self):
        prompt = gemini._build_image_prompt()
        assert "추가 정보:\n" not in prompt

    def test_base_rules_always_present(self):
        prompt = gemini._build_image_prompt()
        assert "category는 반드시 다음 목록 중 하나만 선택" in prompt
        assert "이어폰/에어팟" in prompt

    def test_rekognition_labels_appear_as_hint(self):
        prompt = gemini._build_image_prompt(rekognition_labels=["Earphone", "Electronic"])
        assert "AI 객체 탐지 결과 (힌트): Earphone, Electronic" in prompt
        assert "추가 정보" in prompt

    def test_user_text_appears_as_hint(self):
        prompt = gemini._build_image_prompt(user_text="검정 에어팟 케이스")
        assert "사용자 설명: 검정 에어팟 케이스" in prompt
        assert "추가 정보" in prompt

    def test_both_hints_present(self):
        prompt = gemini._build_image_prompt(
            rekognition_labels=["Backpack", "Blue"],
            user_text="파란 백팩",
        )
        assert "AI 객체 탐지 결과 (힌트): Backpack, Blue" in prompt
        assert "사용자 설명: 파란 백팩" in prompt

    def test_empty_list_treated_as_no_hint(self):
        prompt = gemini._build_image_prompt(rekognition_labels=[])
        assert "추가 정보:\n" not in prompt

    def test_empty_string_treated_as_no_hint(self):
        prompt = gemini._build_image_prompt(user_text="")
        assert "추가 정보:\n" not in prompt

    def test_hint_does_not_override_base_rule(self):
        prompt = gemini._build_image_prompt(rekognition_labels=["X"])
        assert "최종 판단은 이미지 기준으로 해줘" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# _parse
# ─────────────────────────────────────────────────────────────────────────────
class TestParse:
    def test_plain_json(self):
        text = '{"category": "가방", "color": ["검정"], "features": ["애플 로고"]}'
        result = gemini._parse(text)
        assert result == {"category": "가방", "color": ["검정"], "features": ["애플 로고"]}

    def test_fenced_code_block(self):
        text = "```json\n{\"category\": \"지갑\", \"color\": [], \"features\": []}\n```"
        result = gemini._parse(text)
        assert result["category"] == "지갑"

    def test_missing_color_defaults_empty_list(self):
        result = gemini._parse('{"category": "가방", "features": ["흠집"]}')
        assert result["color"] == []

    def test_missing_features_defaults_empty_list(self):
        result = gemini._parse('{"category": "가방", "color": ["파랑"]}')
        assert result["features"] == []

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            gemini._parse("not json")


# ─────────────────────────────────────────────────────────────────────────────
# extract_from_image
# ─────────────────────────────────────────────────────────────────────────────
class TestExtractFromImage:
    def _mock_response(self, category="이어폰/에어팟", color=None, features=None):
        data = {
            "category": category,
            "color": color or ["흰색"],
            "features": features or [],
        }
        mock = MagicMock()
        mock.text = json.dumps(data)
        return mock

    def test_returns_parsed_dict(self):
        with patch.object(gemini._client.models, "generate_content", return_value=self._mock_response()):
            result = gemini.extract_from_image(b"fake_image")
        assert result["category"] == "이어폰/에어팟"

    def test_prompt_includes_rekognition_labels(self):
        with patch.object(gemini._client.models, "generate_content", return_value=self._mock_response()) as mock_gen:
            gemini.extract_from_image(
                b"fake_image",
                rekognition_labels=["Earphone", "Electronic"],
            )
        _, kwargs = mock_gen.call_args
        prompt_text = str(kwargs["contents"][-1])
        assert "Earphone, Electronic" in prompt_text

    def test_prompt_includes_user_text(self):
        with patch.object(gemini._client.models, "generate_content", return_value=self._mock_response()) as mock_gen:
            gemini.extract_from_image(b"fake_image", user_text="에어팟 케이스 분실")
        _, kwargs = mock_gen.call_args
        prompt_text = str(kwargs["contents"][-1])
        assert "에어팟 케이스 분실" in prompt_text

    def test_prompt_omits_hint_section_when_no_hints(self):
        with patch.object(gemini._client.models, "generate_content", return_value=self._mock_response()) as mock_gen:
            gemini.extract_from_image(b"fake_image")
        _, kwargs = mock_gen.call_args
        prompt_text = str(kwargs["contents"][-1])
        assert "AI 객체 탐지 결과 (힌트)" not in prompt_text
        assert "사용자 설명" not in prompt_text


# ─────────────────────────────────────────────────────────────────────────────
# extract_from_text
# ─────────────────────────────────────────────────────────────────────────────
class TestExtractFromText:
    def _mock_response(self, result: dict):
        mock = MagicMock()
        mock.text = json.dumps(result)
        return mock

    def test_returns_parsed_dict(self):
        expected = {"category": "지갑", "color": ["갈색"], "features": ["카드 슬롯"]}
        with patch.object(gemini._client.models, "generate_content", return_value=self._mock_response(expected)):
            result = gemini.extract_from_text("갈색 지갑 분실했어요")
        assert result["category"] == "지갑"
        assert result["color"] == ["갈색"]
