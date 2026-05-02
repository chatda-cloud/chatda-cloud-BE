"""
service.py 단위 테스트.

검증 항목:
  1. Rekognition 라벨이 Gemini에 힌트로 전달되는지
  2. features가 Gemini 결과(한국어)만으로 구성되는지 (Rekognition 영어 라벨 미포함)
  3. item.category가 Gemini 결과로 업데이트되는지
  4. item.image_url이 설정되는지
  5. Gemini 실패 시 Rekognition 라벨이 features fallback으로 남는지
  6. 이미지 다운로드 실패 시 텍스트 경로로 fallback되는지
"""
import asyncio
import io
import os
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from PIL import Image as PILImage

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AWS_REGION", "ap-northeast-2")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from app.tagging.service import process_tags, _build_image_url


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
def _make_item(
    id=1,
    category="기타",
    raw_text="에어팟 케이스 잃어버렸어요",
    image_url=None,
    features=None,
    item_vector=None,
):
    item = MagicMock()
    item.id = id
    item.category = category
    item.raw_text = raw_text
    item.image_url = image_url
    item.features = features
    item.item_vector = item_vector
    return item


def _make_pil_image() -> PILImage.Image:
    return PILImage.new("RGB", (64, 64), color=(128, 128, 128))


def _make_image_bytes() -> bytes:
    buf = io.BytesIO()
    _make_pil_image().save(buf, format="JPEG")
    return buf.getvalue()


def _db_session(item):
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = item
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


REKOGNITION_LABELS = ["Earphone", "Electronic", "Technology"]
GEMINI_RESULT = {
    "category": "이어폰/에어팟",
    "color": ["흰색"],
    "features": ["애플 로고", "왼쪽 스크래치"],
}


# ─────────────────────────────────────────────────────────────────────────────
# _build_image_url
# ─────────────────────────────────────────────────────────────────────────────
class TestBuildImageUrl:
    def test_format(self):
        with patch("app.tagging.service.S3_BUCKET_NAME", "my-bucket"), \
             patch("app.tagging.service.AWS_REGION", "ap-northeast-2"):
            url = _build_image_url("items/1/photo.jpg")
        assert url == "https://my-bucket.s3.ap-northeast-2.amazonaws.com/items/1/photo.jpg"


# ─────────────────────────────────────────────────────────────────────────────
# process_tags — 이미지 있는 경우 (정상 흐름)
# ─────────────────────────────────────────────────────────────────────────────
class TestProcessTagsWithImage:
    def _run(self, item, rekognition_labels=None, gemini_result=None, image_bytes=None):
        image_bytes = image_bytes or _make_image_bytes()
        pil = _make_pil_image()
        db = _db_session(item)

        with (
            patch("app.tagging.service.rekognition.detect_labels", return_value=rekognition_labels or REKOGNITION_LABELS),
            patch("app.tagging.service._download_s3_image", return_value=(image_bytes, pil)),
            patch("app.tagging.service.clip.encode_image_from_pil", return_value=[0.1] * 512),
            patch("app.tagging.service.gemini.extract_from_image", return_value=gemini_result or GEMINI_RESULT) as mock_gemini,
            patch("app.tagging.service.gemini.extract_from_text", return_value=gemini_result or GEMINI_RESULT),
        ):
            asyncio.run(process_tags(item.id, "items/1/photo.jpg", db))
            return item, mock_gemini

    def test_features_contains_only_gemini_output(self):
        item = _make_item()
        item, _ = self._run(item)
        expected = GEMINI_RESULT["color"] + GEMINI_RESULT["features"]
        assert item.features == expected

    def test_features_excludes_rekognition_english_labels(self):
        item = _make_item()
        item, _ = self._run(item)
        for eng_label in REKOGNITION_LABELS:
            assert eng_label not in item.features

    def test_category_updated_from_gemini(self):
        item = _make_item(category="기타")
        self._run(item)
        assert item.category == "이어폰/에어팟"

    def test_image_url_set(self):
        item = _make_item()
        self._run(item)
        assert item.image_url is not None
        assert "items/1/photo.jpg" in item.image_url

    def test_item_vector_set(self):
        item = _make_item()
        self._run(item)
        assert item.item_vector == [0.1] * 512

    def test_gemini_receives_rekognition_labels_as_hint(self):
        item = _make_item(raw_text="에어팟 분실")
        _, mock_gemini = self._run(item)
        # run_in_executor는 위치 인자로 전달: (image_bytes, rekognition_labels, user_text)
        args, _ = mock_gemini.call_args
        assert args[1] == REKOGNITION_LABELS

    def test_gemini_receives_user_text_as_hint(self):
        item = _make_item(raw_text="에어팟 분실")
        _, mock_gemini = self._run(item)
        args, _ = mock_gemini.call_args
        assert args[2] == "에어팟 분실"

    def test_db_commit_called(self):
        item = _make_item()
        db = _db_session(item)
        pil = _make_pil_image()
        image_bytes = _make_image_bytes()
        with (
            patch("app.tagging.service.rekognition.detect_labels", return_value=REKOGNITION_LABELS),
            patch("app.tagging.service._download_s3_image", return_value=(image_bytes, pil)),
            patch("app.tagging.service.clip.encode_image_from_pil", return_value=[0.1] * 512),
            patch("app.tagging.service.gemini.extract_from_image", return_value=GEMINI_RESULT),
            patch("app.tagging.service.gemini.extract_from_text", return_value=GEMINI_RESULT),
        ):
            asyncio.run(process_tags(item.id, "items/1/photo.jpg", db))
        db.commit.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# process_tags — 이미지 다운로드 실패 → 텍스트 fallback
# ─────────────────────────────────────────────────────────────────────────────
class TestProcessTagsImageDownloadFailure:
    def test_falls_back_to_text_gemini(self):
        item = _make_item(raw_text="갈색 지갑")
        db = _db_session(item)
        text_result = {"category": "지갑", "color": ["갈색"], "features": []}

        with (
            patch("app.tagging.service.rekognition.detect_labels", return_value=["Wallet"]),
            patch("app.tagging.service._download_s3_image", side_effect=Exception("S3 error")),
            patch("app.tagging.service.clip.encode_text", return_value=[0.2] * 512),
            patch("app.tagging.service.gemini.extract_from_image") as mock_img,
            patch("app.tagging.service.gemini.extract_from_text", return_value=text_result) as mock_txt,
        ):
            asyncio.run(process_tags(item.id, "items/1/photo.jpg", db))

        mock_img.assert_not_called()
        mock_txt.assert_called_once_with("갈색 지갑")
        assert item.category == "지갑"
        assert "갈색" in item.features

    def test_category_preserved_if_gemini_fails_too(self):
        item = _make_item(category="원래카테고리", raw_text=None)
        db = _db_session(item)

        with (
            patch("app.tagging.service.rekognition.detect_labels", return_value=[]),
            patch("app.tagging.service._download_s3_image", side_effect=Exception()),
            patch("app.tagging.service.clip.encode_text", side_effect=Exception()),
            patch("app.tagging.service.gemini.extract_from_image", side_effect=Exception()),
            patch("app.tagging.service.gemini.extract_from_text", side_effect=Exception()),
        ):
            asyncio.run(process_tags(item.id, "items/1/photo.jpg", db))

        assert item.category == "원래카테고리"


# ─────────────────────────────────────────────────────────────────────────────
# process_tags — Gemini 실패 시 features fallback
# ─────────────────────────────────────────────────────────────────────────────
class TestProcessTagsGeminiFailure:
    def test_rekognition_labels_kept_as_fallback_features(self):
        item = _make_item()
        db = _db_session(item)
        pil = _make_pil_image()
        image_bytes = _make_image_bytes()

        with (
            patch("app.tagging.service.rekognition.detect_labels", return_value=REKOGNITION_LABELS),
            patch("app.tagging.service._download_s3_image", return_value=(image_bytes, pil)),
            patch("app.tagging.service.clip.encode_image_from_pil", return_value=[0.1] * 512),
            patch("app.tagging.service.gemini.extract_from_image", side_effect=Exception("Gemini down")),
            patch("app.tagging.service.gemini.extract_from_text", side_effect=Exception("Gemini down")),
        ):
            asyncio.run(process_tags(item.id, "items/1/photo.jpg", db))

        assert item.features == REKOGNITION_LABELS
        assert item.category == "기타"


# ─────────────────────────────────────────────────────────────────────────────
# process_tags — 아이템 없는 경우
# ─────────────────────────────────────────────────────────────────────────────
class TestProcessTagsItemNotFound:
    def test_exits_gracefully_without_commit(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        asyncio.run(process_tags(999, "items/999/photo.jpg", db))
        db.commit.assert_not_awaited()
