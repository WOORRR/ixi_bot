"""온보딩·보고의 승인/거부 판정 — 순수 함수 (지침서 §4-2·§4-3).

Firestore 접근 없이 판정만 한다. 조회 결과(dict)는 db.py 가 전달하고,
판정 결과에 따른 쓰기·메시지 발송은 onboarding.py / reports.py 가 수행한다.
→ tests/test_gate.py 에서 네트워크 없이 전 분기를 검증한다.
"""

from enum import Enum

# 콜백 데이터 접두어 (admin.py 와 공유). 텔레그램 제한 64바이트 준수 (§7-5).
CALLBACK_DATA_MAX_BYTES = 64


class ContactDecision(Enum):
    """연락처 공유 수신 시 판정 (§4-2 contact 수신 핸들러)."""

    NOT_OWN_CONTACT = "not_own_contact"    # 본인 연락처 아님 — 최우선 거부
    NO_MATCH = "no_match"                  # 명단에 없음 → 실명 문의 폴백
    AUTO_APPROVE = "auto_approve"          # 1건 & unbound & 미바인딩 → 자동 승인
    ALREADY_APPROVED = "already_approved"  # 본인이 이미 승인된 상태로 재공유
    BOUND_TO_OTHER = "bound_to_other"      # 다른 텔레그램 계정에 바인딩됨 (도용 의심)
    REVOKED = "revoked"                    # 차단 계정 — 재온보딩 불가


def decide_contact(
    sender_tg_id: int,
    contact_tg_id: int | None,
    matched_user: dict | None,
) -> ContactDecision:
    """연락처 공유 한 건에 대한 판정.

    matched_user: usr_tel_hmac 일치로 찾은 users 문서 (없으면 None).
    검사 순서 고정 — 본인 여부가 번호 매칭보다 먼저다 (§7-6).
    """
    if contact_tg_id != sender_tg_id:
        return ContactDecision.NOT_OWN_CONTACT
    if matched_user is None:
        return ContactDecision.NO_MATCH

    bound_id = matched_user.get("telegram_user_id")
    if bound_id is not None and bound_id != sender_tg_id:
        return ContactDecision.BOUND_TO_OTHER
    if matched_user.get("status") == "revoked":
        return ContactDecision.REVOKED
    if matched_user.get("status") == "approved":
        return ContactDecision.ALREADY_APPROVED
    if matched_user.get("status") == "unbound" and bound_id is None:
        return ContactDecision.AUTO_APPROVE
    # 불일치 상태(예: unbound인데 바인딩 잔존) — 자동 승인하지 않고 도용 의심으로 처리
    return ContactDecision.BOUND_TO_OTHER


class StartDecision(Enum):
    """/start 수신 시 판정 (§4-2 진입점 B)."""

    APPROVED = "approved"      # 보고 안내 + 폼 버튼
    REVOKED = "revoked"        # 이용 제한 안내
    NEED_ONBOARDING = "need_onboarding"  # 연락처 공유 안내


def decide_start(user: dict | None) -> StartDecision:
    if user is None:
        return StartDecision.NEED_ONBOARDING
    if user.get("status") == "approved":
        return StartDecision.APPROVED
    if user.get("status") == "revoked":
        return StartDecision.REVOKED
    return StartDecision.NEED_ONBOARDING


def report_allowed(user: dict | None) -> bool:
    """web_app_data 게이트 (§4-3-1): 승인된 사용자만 기록한다."""
    return user is not None and user.get("status") == "approved"


def can_bind(user: dict | None) -> bool:
    """수작업 승인(jr_ap) 시점 재확인: 여전히 unbound·미바인딩인가 (§4-2 관리자 콜백)."""
    return (
        user is not None
        and user.get("status") == "unbound"
        and user.get("telegram_user_id") is None
    )


def build_callback_data(*parts: object) -> str:
    """콜백 데이터 조립 + 64바이트 제한 검증 (§7-5)."""
    data = ":".join(str(p) for p in parts)
    if len(data.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
        raise ValueError(f"callback_data 가 64바이트를 초과합니다: {data!r}")
    return data
