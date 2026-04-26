"""Lambda handler 로컬 테스트 — python lambda/test_local.py"""
import os
import sys

# 프로젝트 루트의 .env 로드
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import json
from handler import lambda_handler

mock_event = {
    "body": json.dumps({
        "itemId": 1,
        "filename": "test_jacket.jpg",
        "contentType": "image/jpeg",
    })
}

result = lambda_handler(mock_event, context=None)
print("status:", result["statusCode"])
print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
