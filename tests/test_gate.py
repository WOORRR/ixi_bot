"""gate.py 승인/거부 분기 전수 테스트 — Firestore 불필요 (지침서 Phase 3)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate import (
    ContactDecision,
    StartDecision,
    build_callback_data,
    can_bind,
    decide_contact,
    decide_start,
    report_allowed,
)

ME = 111111111
OTHER = 222222222


def user(status="unbound", telegram_user_id=None):
    return {"status": status, "telegram_user_id": telegram_user_id, "usr_nm": "홍길동"}


class TestDecideContact:
    def test_not_own_contact_rejected_first(self):
        # 사칭 차단이 최우선 — 매칭 결과와 무관하게 거부 (§7-6)
        assert (
            decide_contact(ME, OTHER, user("unbound"))
            == ContactDecision.NOT_OWN_CONTACT
        )
        assert decide_contact(ME, None, None) == ContactDecision.NOT_OWN_CONTACT

    def test_no_match_falls_back_to_name(self):
        assert decide_contact(ME, ME, None) == ContactDecision.NO_MATCH

    def test_unbound_auto_approve(self):
        assert decide_contact(ME, ME, user("unbound")) == ContactDecision.AUTO_APPROVE

    def test_bound_to_other_suspected(self):
        assert (
            decide_contact(ME, ME, user("approved", OTHER))
            == ContactDecision.BOUND_TO_OTHER
        )

    def test_revoked_no_reonboarding(self):
        assert decide_contact(ME, ME, user("revoked", ME)) == ContactDecision.REVOKED
        assert decide_contact(ME, ME, user("revoked")) == ContactDecision.REVOKED

    def test_already_approved_self(self):
        assert (
            decide_contact(ME, ME, user("approved", ME))
            == ContactDecision.ALREADY_APPROVED
        )

    def test_inconsistent_state_not_auto_approved(self):
        # unbound인데 바인딩이 남은 이상 상태 — 자동 승인 금지
        assert (
            decide_contact(ME, ME, user("unbound", ME))
            == ContactDecision.BOUND_TO_OTHER
        )


class TestDecideStart:
    def test_unknown_needs_onboarding(self):
        assert decide_start(None) == StartDecision.NEED_ONBOARDING

    def test_approved(self):
        assert decide_start(user("approved", ME)) == StartDecision.APPROVED

    def test_revoked(self):
        assert decide_start(user("revoked", ME)) == StartDecision.REVOKED

    def test_unbound_needs_onboarding(self):
        assert decide_start(user("unbound")) == StartDecision.NEED_ONBOARDING


class TestReportGate:
    def test_unknown_blocked(self):
        assert not report_allowed(None)

    def test_unbound_blocked(self):
        assert not report_allowed(user("unbound"))

    def test_revoked_blocked(self):
        assert not report_allowed(user("revoked", ME))

    def test_approved_allowed(self):
        assert report_allowed(user("approved", ME))


class TestCanBind:
    def test_unbound_ok(self):
        assert can_bind(user("unbound"))

    def test_already_bound_rejected(self):
        assert not can_bind(user("approved", ME))
        assert not can_bind(user("unbound", ME))

    def test_missing_rejected(self):
        assert not can_bind(None)


class TestCallbackData:
    def test_typical_formats_within_limit(self):
        uuid = "33cb50f5-2ea6-4460-974d-bf184bd6217c"
        tg_id = 9999999999  # 텔레그램 ID 상한 근처
        for data in (
            build_callback_data("jr_ap", tg_id, uuid),
            build_callback_data("jr_rej", tg_id),
            build_callback_data("rv_ok", uuid),
            build_callback_data("rv_block", uuid),
            build_callback_data("rvk", uuid),
            build_callback_data("ubd", uuid),
        ):
            assert len(data.encode("utf-8")) <= 64

    def test_overlong_raises(self):
        with pytest.raises(ValueError):
            build_callback_data("x" * 65)
