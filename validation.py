"""폼 제출 데이터의 서버 측 재검증 (기획서 §4-2).

폼 페이지는 공개 URL이므로 클라이언트 검증을 신뢰하지 않고,
봇이 수신한 데이터를 여기서 다시 전부 검사한다.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from names import NAMES

KST = ZoneInfo("Asia/Seoul")
TIME_FORMAT = "%Y-%m-%d %H:%M"
# 폼의 max(미래 차단)는 폼이 열린 시각 기준이므로 수신 시각 기준 +2분 허용 오차를 둔다.
FUTURE_TOLERANCE = timedelta(minutes=2)
MAX_TEXT_LENGTH = 200


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None
    report: dict | None = None


def _fail(message: str) -> ValidationResult:
    return ValidationResult(ok=False, error=message)


def validate_report(raw: str, *, now: datetime | None = None) -> ValidationResult:
    """web_app_data 로 수신한 raw JSON 문자열을 검증한다.

    통과 시 report = {"name", "symptom_time", "symptom_text"} 를 담아 반환.
    """
    # (1) JSON 스키마
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _fail("데이터 형식이 올바르지 않습니다 (JSON 아님)")
    if not isinstance(data, dict):
        return _fail("데이터 형식이 올바르지 않습니다")

    name = data.get("name")
    symptom_time = data.get("symptom_time")
    symptom_text = data.get("symptom_text")
    if not all(isinstance(v, str) for v in (name, symptom_time, symptom_text)):
        return _fail("필수 항목(이름·시각·증상 내용)이 누락되었습니다")

    # (2) 이름이 후보 리스트에 존재
    if name not in NAMES:
        return _fail("이름이 목록에 없습니다. 목록에서 선택해 주세요")

    # (3) 시각 형식 및 미래 아님 (과거 하한 없음)
    try:
        parsed = datetime.strptime(symptom_time, TIME_FORMAT).replace(tzinfo=KST)
    except ValueError:
        return _fail("시각 형식이 올바르지 않습니다 (YYYY-MM-DD HH:MM)")
    current = now if now is not None else datetime.now(KST)
    if parsed > current + FUTURE_TOLERANCE:
        return _fail("미래 시각은 선택할 수 없습니다")

    # (4) 텍스트 1~200자 (공백만 입력은 무효)
    text = symptom_text.strip()
    if not text:
        return _fail("증상 내용을 입력해 주세요")
    if len(text) > MAX_TEXT_LENGTH:
        return _fail(f"증상 내용은 최대 {MAX_TEXT_LENGTH}자까지 입력할 수 있습니다")

    return ValidationResult(
        ok=True,
        report={"name": name, "symptom_time": symptom_time, "symptom_text": text},
    )
