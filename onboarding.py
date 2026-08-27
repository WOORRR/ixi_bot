"""신규 멤버 온보딩 상태 기계 (지침서 §4-2).

경로 1 (자동): 그룹 입장 → 1:1 /start → 연락처 공유 → HMAC 매칭 → 즉시 승인(후심사 대기)
경로 2 (폴백): 번호 불일치 → 실명 입력 → 관리자 수작업 승인/거절

대화 상태는 메모리에 두지 않고 join_requests.state 로 관리한다 (§7-9).
사용자 대면 메시지에 실명을 출력하지 않는다 (§1-4).
"""

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import ContextTypes

import db
from config import ADMIN_CHAT_ID, FORM_URL, GROUP_CHAT_ID
from gate import ContactDecision, StartDecision, build_callback_data, decide_contact, decide_start
from phone import normalize_tel, tel_hmac

logger = logging.getLogger("ixibot.onboarding")


# ── 키보드 ──────────────────────────────────────────────────


def form_keyboard() -> ReplyKeyboardMarkup:
    """Mini App 폼을 여는 키보드 버튼.

    주의: sendData는 ReplyKeyboardMarkup의 web_app 버튼으로 열었을 때만
    봇에 전달된다 (인라인 버튼 사용 금지 — §1-6).
    """
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📝 증상 보고하기", web_app=WebAppInfo(url=FORM_URL))]],
        resize_keyboard=True,
        is_persistent=True,
    )


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 연락처 공유", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _display_username(username: str | None) -> str:
    """관리자 알림용 — username 이 없으면 None 노출 방지 (§7-8)."""
    return f"@{username}" if username else "(유저네임 없음)"


REVOKED_MESSAGE = "이용이 제한된 계정입니다. 관리자에게 문의하세요."
ONBOARDING_MESSAGE = (
    "안녕하세요, IxiBot입니다 🙂\n"
    "서비스 이용 중 겪은 오류 증상을 수집하고 있어요.\n\n"
    "이용을 위해 먼저 등록 확인이 필요합니다.\n"
    "아래 [📱 연락처 공유] 버튼을 눌러 본인 확인을 진행해 주세요."
)
APPROVED_START_MESSAGE = (
    "안녕하세요, IxiBot입니다 🙂\n"
    "아래 [📝 증상 보고하기] 버튼을 누르면 보고 폼이 열립니다.\n"
    "여러 번 제출하셔도 됩니다."
)


# ── 진입점 A — 그룹 입장 ─────────────────────────────────────


async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """그룹 입장 감지 → 그룹방에 환영 메시지 + 1:1 딥링크 버튼 (§4-2 진입점 A).

    그룹방 메시지에 실명 금지 (§1-4). GROUP_CHAT_ID 외의 방은 무시 (§7-7).
    """
    cm = update.chat_member
    if cm is None or cm.chat.id != GROUP_CHAT_ID:
        return

    def _is_member(member) -> bool:
        if member.status in ("member", "administrator", "creator"):
            return True
        return member.status == "restricted" and getattr(member, "is_member", False)

    if _is_member(cm.old_chat_member) or not _is_member(cm.new_chat_member):
        return  # (밖 → member) 전이만 처리

    deeplink = f"https://t.me/{context.bot.username}?start=verify"
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=(
            "환영합니다! 👋\n"
            "오류 증상 보고를 이용하시려면 아래 버튼으로 봇과 1:1 대화에서 "
            "등록 확인을 진행해 주세요."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ 등록 확인하기", url=deeplink)]]
        ),
    )


# ── 진입점 B — 1:1 /start ───────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """딥링크 파라미터 verify/report 공통 (§4-2 진입점 B)."""
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    found = await db.find_user_by_telegram_id(user.id)
    decision = decide_start(found)

    if decision == StartDecision.APPROVED:
        await message.reply_text(APPROVED_START_MESSAGE, reply_markup=form_keyboard())
    elif decision == StartDecision.REVOKED:
        await message.reply_text(REVOKED_MESSAGE)
    else:
        await message.reply_text(ONBOARDING_MESSAGE, reply_markup=contact_keyboard())


# ── contact 수신 ────────────────────────────────────────────


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    sender = update.effective_user
    if message is None or sender is None or message.contact is None:
        return
    contact = message.contact

    # 번호 정규화 실패(해외 번호 등)는 명단 불일치와 동일하게 폴백 처리
    matched = None
    masked = None
    if contact.user_id == sender.id:
        try:
            e164 = normalize_tel(contact.phone_number)
        except ValueError:
            e164 = None
        if e164 is not None:
            matched = await db.find_user_by_tel_hmac(tel_hmac(e164))
            if matched is not None:
                masked = matched.get("usr_tel_masked", "")

    decision = decide_contact(sender.id, contact.user_id, matched)
    logger.info("contact 판정 (tg_id=%s): %s", sender.id, decision.value)

    if decision == ContactDecision.NOT_OWN_CONTACT:
        await message.reply_text(
            "본인의 연락처만 공유할 수 있습니다.\n"
            "아래 버튼으로 본인 연락처를 공유해 주세요.",
            reply_markup=contact_keyboard(),
        )
        return

    if decision == ContactDecision.NO_MATCH:
        await db.upsert_join_request(
            sender.id,
            {
                "state": "awaiting_name",
                "claimed_name": None,
                "telegram_username": sender.username,
                "candidate_usr_ids": [],
                "decided_at": None,
            },
        )
        await message.reply_text(
            "명단에서 확인되지 않았습니다.\n확인을 위해 실명을 입력해 주세요."
        )
        return

    if decision == ContactDecision.REVOKED:
        await message.reply_text(REVOKED_MESSAGE)
        return

    if decision == ContactDecision.ALREADY_APPROVED:
        await message.reply_text(
            "이미 확인된 계정입니다 ✅", reply_markup=form_keyboard()
        )
        return

    if decision == ContactDecision.BOUND_TO_OTHER:
        await message.reply_text(
            "확인할 수 없는 연락처입니다. 관리자에게 문의하세요."
        )
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "⚠️ 도용 의심\n"
                f"명단의 번호가 이미 다른 계정에 연결되어 있는데, 다른 사용자가 "
                f"해당 번호로 온보딩을 시도했습니다.\n"
                f"{matched.get('usr_nm')} ({masked})\n"
                f"시도자: {_display_username(sender.username)} / tg_id={sender.id}"
            ),
        )
        return

    # AUTO_APPROVE — 트랜잭션 바인딩 (§4-2)
    ok = await db.bind_user(
        matched["usr_id"], sender.id, sender.username, approval_method="phone_auto"
    )
    if not ok:
        # 경합으로 이미 바인딩됨 — 도용 의심과 동일하게 보수 처리
        await message.reply_text("처리할 수 없습니다. 관리자에게 문의하세요.")
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "⚠️ 자동 승인 실패 (경합/중복)\n"
                f"{matched.get('usr_nm')} ({masked})\n"
                f"시도자: {_display_username(sender.username)} / tg_id={sender.id}"
            ),
        )
        return

    await message.reply_text("확인되었습니다 ✅", reply_markup=form_keyboard())
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            "🔔 자동 승인(후심사 대기)\n"
            f"{matched.get('usr_nm')} ({masked})\n"
            f"{_display_username(sender.username)} / tg_id={sender.id}"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ 확인", callback_data=build_callback_data("rv_ok", matched["usr_id"])
                    ),
                    InlineKeyboardButton(
                        "🚫 차단",
                        callback_data=build_callback_data("rv_block", matched["usr_id"]),
                    ),
                ]
            ]
        ),
    )


# ── 실명 텍스트 수신 (폴백 경로) ──────────────────────────────


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """join_requests.state == "awaiting_name" 일 때만 반응한다."""
    message = update.effective_message
    sender = update.effective_user
    if message is None or sender is None or not message.text:
        return

    jr = await db.get_join_request(sender.id)
    if jr is None or jr.get("state") != "awaiting_name":
        return

    claimed_name = message.text.strip()
    if not claimed_name:
        return

    candidates = await db.find_unbound_users_by_name(claimed_name)
    await db.upsert_join_request(
        sender.id,
        {
            "state": "pending",
            "claimed_name": claimed_name,
            "telegram_username": sender.username,
            "candidate_usr_ids": [c["usr_id"] for c in candidates],
        },
    )
    await message.reply_text("관리자 확인 후 안내드리겠습니다.")

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            "🙋 수작업 확인 요청\n"
            f"입력 실명: {claimed_name}\n"
            f"{_display_username(sender.username)} / tg_id={sender.id}\n"
            f"명단 후보: {len(candidates)}건"
        ),
        reply_markup=join_request_buttons(sender.id, candidates),
    )


def join_request_buttons(tg_id: int, candidates: list[dict]) -> InlineKeyboardMarkup:
    """후보별 승인 버튼 + 거절 버튼 (후보 0건이면 거절만) — /pending 재제공에도 사용."""
    rows = [
        [
            InlineKeyboardButton(
                f"✅ {c['usr_nm']} ({c.get('usr_tel_masked', '')})로 승인",
                callback_data=build_callback_data("jr_ap", tg_id, c["usr_id"]),
            )
        ]
        for c in candidates
    ]
    rows.append(
        [InlineKeyboardButton("❌ 거절", callback_data=build_callback_data("jr_rej", tg_id))]
    )
    return InlineKeyboardMarkup(rows)
