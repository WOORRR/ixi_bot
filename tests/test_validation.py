"""서버 측 재검증 로직 단위 테스트 (v0.2 — 이름 검증 제거)."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation import KST, MAX_TEXT_LENGTH, validate_report

NOW = datetime(2026, 8, 26, 14, 35, tzinfo=KST)


def make_raw(**overrides):
    data = {
        "symptom_time": "2026-08-26 14:00",
        "symptom_text": "앱이 갑자기 멈췄습니다",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class TestSchema:
    def test_valid_report_passes(self):
        result = validate_report(make_raw(), now=NOW)
        assert result.ok
        assert result.report["symptom_time"] == "2026-08-26 14:00"
        assert result.report["symptom_text"] == "앱이 갑자기 멈췄습니다"
        ts = result.report["symptom_time_ts"]
        assert ts == datetime(2026, 8, 26, 14, 0, tzinfo=KST)
        assert ts.tzinfo is not None  # naive 금지 (§7-2)

    def test_invalid_json(self):
        assert not validate_report("not json{{", now=NOW).ok

    def test_non_dict_json(self):
        assert not validate_report('["a", "b"]', now=NOW).ok

    def test_missing_field(self):
        raw = json.dumps({"symptom_time": "2026-08-26 14:00"})
        assert not validate_report(raw, now=NOW).ok

    def test_extra_key_rejected(self):
        # v0.1 페이로드(name 포함) 등 두 키 외 스키마는 거부
        raw = json.dumps(
            {
                "name": "홍길동",
                "symptom_time": "2026-08-26 14:00",
                "symptom_text": "증상",
            },
            ensure_ascii=False,
        )
        assert not validate_report(raw, now=NOW).ok

    def test_non_string_field(self):
        assert not validate_report(make_raw(symptom_text=123), now=NOW).ok


class TestTime:
    def test_bad_format_iso_t(self):
        assert not validate_report(make_raw(symptom_time="2026-08-26T14:00"), now=NOW).ok

    def test_bad_format_no_minutes(self):
        assert not validate_report(make_raw(symptom_time="2026-08-26 14"), now=NOW).ok

    def test_impossible_date(self):
        assert not validate_report(make_raw(symptom_time="2026-02-30 10:00"), now=NOW).ok

    def test_future_rejected(self):
        future = (NOW + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        result = validate_report(make_raw(symptom_time=future), now=NOW)
        assert not result.ok
        assert "미래" in result.error

    def test_future_within_tolerance_accepted(self):
        near = (NOW + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
        assert validate_report(make_raw(symptom_time=near), now=NOW).ok

    def test_no_past_limit(self):
        assert validate_report(make_raw(symptom_time="1990-01-01 00:00"), now=NOW).ok


class TestText:
    def test_empty_text(self):
        assert not validate_report(make_raw(symptom_text=""), now=NOW).ok

    def test_whitespace_only(self):
        assert not validate_report(make_raw(symptom_text="   \n  "), now=NOW).ok

    def test_max_length_ok(self):
        assert validate_report(make_raw(symptom_text="가" * MAX_TEXT_LENGTH), now=NOW).ok

    def test_over_max_length(self):
        result = validate_report(
            make_raw(symptom_text="가" * (MAX_TEXT_LENGTH + 1)), now=NOW
        )
        assert not result.ok

    def test_text_is_stripped(self):
        result = validate_report(make_raw(symptom_text="  증상  "), now=NOW)
        assert result.ok
        assert result.report["symptom_text"] == "증상"
