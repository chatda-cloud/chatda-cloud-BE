import json
import google.generativeai as genai
from app.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel("gemini-1.5-flash")


def extract_tags(description: str) -> list[str]:
    prompt = (
        "아래 분실물 설명에서 색상, 형태, 특이사항 등 핵심 특징을 "
        "JSON 배열 형태로만 응답하세요. 예: [\"노란 별 스티커\", \"왼쪽 스크래치\"]\n\n"
        f"설명: {description}"
    )
    response = _model.generate_content(prompt)
    return json.loads(response.text)
