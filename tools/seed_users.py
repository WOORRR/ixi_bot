"""user_list_Sql.txt → Firestore users 컬렉션 시드 (지침서 Phase 4).

사용법:
    1. user_list_Sql.txt 끝에 관리자 행(§2-1-1)을 이어 붙인다 (합계 81행).
    2. GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_CLOUD_PROJECT 설정 후:
       python tools/seed_users.py [경로 (기본: ./user_list_Sql.txt)]

- 정확히 81건(명단 80 + 관리자 1)·중복 없음을 assert 후 적재한다.
- 이미 존재하는 문서는 건너뛴다 (재실행 안전).
- 적재 후 임의 1건을 decrypt_tel 로 self-check 한다 (§1-3 허용 호출처).
- 출력에 평문 전화번호를 절대 찍지 않는다 (§1-2) — 마스킹만 사용한다.
"""

import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXPECTED_COUNT = 81  # 명단 80 + 관리자 1 (§2-1-1)

_ROW_RE = re.compile(
    r"select\s+'([^']*)'(?:\s+as\s+usr_nm)?\s*,\s*"
    r"'([^']*)'(?:\s+as\s+usr_tel)?\s*,\s*"
    r"'([^']*)'(?:\s+as\s+usr_id)?",
    re.IGNORECASE,
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def parse_user_list(text: str) -> list[tuple[str, str, str]]:
    """SQL union all 텍스트 → [(usr_nm, usr_tel, usr_id), ...].

    첫 행에만 `as` 별칭이 붙는 형식과 전 행 별칭 형식을 모두 허용한다.
    """
    rows = _ROW_RE.findall(text)
    parsed = [(nm.strip(), tel.strip(), uid.strip()) for nm, tel, uid in rows]
    for nm, tel, uid in parsed:
        if not nm:
            raise ValueError("빈 이름 행이 있습니다")
        if not _UUID_RE.match(uid):
            raise ValueError(f"UUID 형식이 아닌 usr_id 가 있습니다: {uid!r}")
    return parsed


def check_integrity(rows: list[tuple[str, str, str]]) -> None:
    """81건·중복 없음 assert (§2-1-1)."""
    assert len(rows) == EXPECTED_COUNT, (
        f"행 수가 {len(rows)}건입니다 — {EXPECTED_COUNT}건(명단 80 + 관리자 1)이어야 합니다. "
        "user_list_Sql.txt 끝에 관리자 행을 추가했는지 확인하세요 (지침서 §2-1-1)."
    )
    names = [r[0] for r in rows]
    tels = [r[1] for r in rows]
    uids = [r[2] for r in rows]
    assert len(set(names)) == len(names), "이름에 중복이 있습니다"
    assert len(set(tels)) == len(tels), "전화번호에 중복이 있습니다"
    assert len(set(uids)) == len(uids), "UUID에 중복이 있습니다"


def build_records(rows: list[tuple[str, str, str]]) -> list[dict]:
    from phone import encrypt_tel, mask_tel, normalize_tel, tel_hmac

    records = []
    for nm, tel, uid in rows:
        e164 = normalize_tel(tel)
        records.append(
            {
                "usr_id": uid,
                "usr_nm": nm,
                "usr_tel_enc": encrypt_tel(e164),
                "usr_tel_hmac": tel_hmac(e164),
                "usr_tel_masked": mask_tel(tel),
            }
        )
    return records


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("user_list_Sql.txt")
    if not path.exists():
        raise SystemExit(f"{path} 파일이 없습니다.")

    rows = parse_user_list(path.read_text(encoding="utf-8"))
    check_integrity(rows)
    records = build_records(rows)

    import db
    from phone import decrypt_tel, normalize_tel

    summary = db.seed_upsert_users(records)

    # self-check: 임의 1건을 Firestore 에서 다시 읽어 복호 → 원본과 일치 확인.
    # (§1-3: decrypt_tel 허용 호출처. 평문은 비교만 하고 출력하지 않는다.)
    sample = random.choice(records)
    stored_enc = db.seed_get_user_enc(sample["usr_id"])
    assert stored_enc is not None, "self-check 실패: 적재된 문서를 찾지 못했습니다"
    src_row = next(r for r in rows if r[2] == sample["usr_id"])
    assert decrypt_tel(stored_enc) == normalize_tel(src_row[1]), (
        "self-check 실패: 복호 결과가 원본과 다릅니다"
    )

    print(
        f"시드 완료 ✅  신규 {summary['created']}건 / 건너뜀 {summary['skipped']}건 "
        f"(총 {len(records)}건)"
    )
    print(f"self-check 통과: {sample['usr_nm']} ({sample['usr_tel_masked']}) 암복호 왕복 일치")


if __name__ == "__main__":
    main()
