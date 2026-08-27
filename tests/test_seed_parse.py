"""tools/seed_users.py 파서 테스트 — 픽스처는 전부 가짜 데이터 (지침서 §1-5)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.seed_users import check_integrity, parse_user_list

# 첫 행만 as 별칭 — 실제 파일과 같은 형식. 값은 모두 가짜다.
FAKE_SQL = (
    "select '가나다' as usr_nm, '010-1111-0001' as usr_tel,"
    " '00000000-0000-4000-8000-000000000001' as usr_id union all\n"
    "select '라마바' , '010-1111-0002' , '00000000-0000-4000-8000-000000000002' union all\n"
    "select '사아자' , '010-1111-0003' , '00000000-0000-4000-8000-000000000003'"
)


class TestParse:
    def test_parses_all_rows(self):
        rows = parse_user_list(FAKE_SQL)
        assert rows == [
            ("가나다", "010-1111-0001", "00000000-0000-4000-8000-000000000001"),
            ("라마바", "010-1111-0002", "00000000-0000-4000-8000-000000000002"),
            ("사아자", "010-1111-0003", "00000000-0000-4000-8000-000000000003"),
        ]

    def test_all_rows_aliased_also_ok(self):
        text = (
            "select '가나다' as usr_nm, '010-1111-0001' as usr_tel,"
            " '00000000-0000-4000-8000-000000000001' as usr_id"
        )
        assert len(parse_user_list(text)) == 1

    def test_bad_uuid_raises(self):
        with pytest.raises(ValueError):
            parse_user_list("select '가나다' , '010-1111-0001' , 'not-a-uuid'")


class TestIntegrity:
    def _rows(self, n):
        return [
            (f"이름{i}", f"010-2222-{i:04d}", f"00000000-0000-4000-8000-{i:012d}")
            for i in range(n)
        ]

    def test_81_rows_pass(self):
        check_integrity(self._rows(81))

    def test_80_rows_fail_with_admin_hint(self):
        with pytest.raises(AssertionError, match="관리자"):
            check_integrity(self._rows(80))

    def test_duplicate_tel_fails(self):
        rows = self._rows(81)
        rows[1] = (rows[1][0], rows[0][1], rows[1][2])
        with pytest.raises(AssertionError, match="전화번호"):
            check_integrity(rows)

    def test_duplicate_uuid_fails(self):
        rows = self._rows(81)
        rows[1] = (rows[1][0], rows[1][1], rows[0][2])
        with pytest.raises(AssertionError, match="UUID"):
            check_integrity(rows)
