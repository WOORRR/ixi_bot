"""제출 데이터 임시 저장 — v0.1: JSONL 파일.

v0.2에서 DB 저장으로 교체하기 쉽도록 저장 로직을 이 파일 한 곳에 격리한다.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
REPORTS_FILE = Path(__file__).resolve().parent / "reports.jsonl"


def save_report(report: dict, telegram_user_id: int | None) -> None:
    """검증을 통과한 보고 1건을 reports.jsonl 에 한 줄로 추가한다."""
    record = {
        "telegram_user_id": telegram_user_id,
        "name": report["name"],
        "symptom_time": report["symptom_time"],
        "symptom_text": report["symptom_text"],
        "submitted_at": datetime.now(KST).isoformat(timespec="seconds"),
    }
    with REPORTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
