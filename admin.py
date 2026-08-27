"""관리자 콜백·명령 (지침서 §4-2 관리자 콜백/명령).

- callback_query 는 ADMIN_CHAT_ID 에서 온 것만 처리한다.
- 모든 상태 전이는 db.py 의 트랜잭션 함수로 수행 — 중복 클릭 시 "이미 처리되었습니다".
- 처리 후 answer_callback_query + 원 메시지를 처리 결과로 edit.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import db
from config import ADMIN_CHAT_ID
from gate import build_callback_data
from onboarding import (
    REVOKED_MESSAGE,
    _display_username,
    form_keyboard,
    join_request_buttons,
)

logger = logging.getLogger("ixibot.admin")

ALREADY_DONE = "이미 처리되었습니다"


async def _notify_user(context, chat_id: int, text: str, reply_markup=None) -> None:
    """사용자에게 처리 결과 안내. 차단 등으로 실패해도 관리자 흐름은 계속한다."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    except TelegramError:
        logger.warning("사용자 알림 실패 (chat_id=%s)", chat_id)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    if query.from_user is None or query.from_user.id != ADMIN_CHAT_ID:
        await query.answer()
        return

    parts = (query.data or "").split(":")
    action = parts[0]

    async def finish(popup: str, result_line: str | None = None) -> None:
        await query.answer(popup)
        if result_line is not None and query.message is not None:
            base = query.message.text or ""
            try:
                await query.edit_message_text(f"{base}\n\n{result_line}")
            except TelegramError:
                pass  # 내용 동일 등으로 edit 실패해도 무시

    try:
        if action == "jr_ap" and len(parts) == 3:
            tg_id, usr_id = int(parts[1]), parts[2]
            jr = await db.get_join_request(tg_id)
            username = jr.get("telegram_username") if jr else None
            result = await db.approve_join_request(tg_id, usr_id, username)
            if result == "ok":
                user = await db.get_user(usr_id)
                await _notify_user(
                    context, tg_id, "등록이 확인되었습니다 ✅", reply_markup=form_keyboard()
                )
                await finish("승인 완료", f"✅ 승인 완료 — {user['usr_nm'] if user else usr_id}")
            elif result == "user_taken":
                await finish(
                    "승인 불가", "⚠️ 해당 명단 항목이 이미 다른 계정에 연결되어 승인할 수 없습니다"
                )
            else:
                await finish(ALREADY_DONE)

        elif action == "jr_rej" and len(parts) == 2:
            tg_id = int(parts[1])
            if await db.reject_join_request(tg_id):
                await _notify_user(
                    context,
                    tg_id,
                    "명단에서 확인하지 못했습니다.\n"
                    "정보가 잘못 입력되었다면 [📱 연락처 공유]부터 다시 시도해 주세요.",
                )
                await finish("거절 완료", "❌ 거절 처리했습니다")
            else:
                await finish(ALREADY_DONE)

        elif action == "rv_ok" and len(parts) == 2:
            if await db.set_review_done(parts[1]):
                await finish("확인 완료", "✅ 후심사 종결")
            else:
                await finish(ALREADY_DONE)

        elif action in ("rv_block", "rvk") and len(parts) == 2:
            usr_id = parts[1]
            user = await db.get_user(usr_id)
            if await db.revoke_user(usr_id):
                if user and user.get("telegram_user_id"):
                    await _notify_user(context, user["telegram_user_id"], REVOKED_MESSAGE)
                await finish("차단 완료", f"🚫 차단 완료 — {user['usr_nm'] if user else usr_id}")
            else:
                await finish(ALREADY_DONE)

        elif action == "ubd" and len(parts) == 2:
            user = await db.get_user(parts[1])
            if await db.unbind_user(parts[1]):
                await finish(
                    "해제 완료", f"🔓 연결 해제 완료 — {user['usr_nm'] if user else parts[1]} (재온보딩 가능)"
                )
            else:
                await finish(ALREADY_DONE)

        else:
            await query.answer("알 수 없는 요청입니다")
    except Exception:
        logger.exception("콜백 처리 실패 (data=%s)", query.data)
        await query.answer("처리 중 오류가 발생했습니다")


# ── 관리자 명령 ──────────────────────────────────────────────


def _is_admin(update: Update) -> bool:
    return (
        update.effective_chat is not None and update.effective_chat.id == ADMIN_CHAT_ID
    )


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """수작업 대기 + 후심사 대기 목록, 각 항목에 inline 버튼 재제공."""
    if not _is_admin(update):
        return
    message = update.effective_message

    pending = await db.list_pending_join_requests()
    reviews = await db.list_needs_review_users()
    if not pending and not reviews:
        await message.reply_text("대기 중인 항목이 없습니다 ✅")
        return

    for jr in pending:
        tg_id = jr["telegram_user_id"]
        candidates = [
            u
            for u in [await db.get_user(uid) for uid in jr.get("candidate_usr_ids", [])]
            if u is not None and u.get("status") == "unbound"
        ]
        await message.reply_text(
            "🙋 수작업 확인 대기\n"
            f"입력 실명: {jr.get('claimed_name')}\n"
            f"{_display_username(jr.get('telegram_username'))} / tg_id={tg_id}\n"
            f"명단 후보: {len(candidates)}건",
            reply_markup=join_request_buttons(tg_id, candidates),
        )

    for user in reviews:
        await message.reply_text(
            "🔔 후심사 대기\n"
            f"{user['usr_nm']} ({user.get('usr_tel_masked', '')})\n"
            f"{_display_username(user.get('telegram_username'))} / tg_id={user.get('telegram_user_id')}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ 확인", callback_data=build_callback_data("rv_ok", user["usr_id"])
                        ),
                        InlineKeyboardButton(
                            "🚫 차단",
                            callback_data=build_callback_data("rv_block", user["usr_id"]),
                        ),
                    ]
                ]
            ),
        )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    counts = await db.count_users_by_status()
    await update.effective_message.reply_text(
        f"👥 사용자 현황\n승인 {counts['approved']} / 미연결 {counts['unbound']} / 차단 {counts['revoked']}"
    )


async def _bound_user_menu(update: Update, *, action: str, title: str, statuses: set[str]) -> None:
    users = [u for u in await db.list_bound_users() if u.get("status") in statuses]
    if not users:
        await update.effective_message.reply_text("대상 사용자가 없습니다.")
        return
    buttons = [
        [
            InlineKeyboardButton(
                f"{u['usr_nm']} ({u.get('usr_tel_masked', '')})",
                callback_data=build_callback_data(action, u["usr_id"]),
            )
        ]
        for u in sorted(users, key=lambda u: u["usr_nm"])
    ]
    await update.effective_message.reply_text(
        title, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    await _bound_user_menu(
        update, action="rvk", title="🚫 차단할 사용자를 선택하세요:", statuses={"approved"}
    )


async def cmd_unbind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    # revoked 도 포함 — 차단 해제 후 재온보딩 경로 (§6 DoD)
    await _bound_user_menu(
        update,
        action="ubd",
        title="🔓 연결 해제할 사용자를 선택하세요 (해제 시 재온보딩 필요):",
        statuses={"approved", "revoked"},
    )


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """누구든 호출 가능 — ADMIN_CHAT_ID/GROUP_CHAT_ID 설정용 헬퍼."""
    chat = update.effective_chat
    if chat is None:
        return
    await update.effective_message.reply_text(f"chat_id: {chat.id}")
