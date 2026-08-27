"""보고 수신 (지침서 §4-3).

게이트: 승인된(approved) 사용자만 기록한다. 미승인 web_app_data 는 기록하지 않는다.
모든 보고는 제출자의 usr_id 로 귀속 기록된다 (§0 — v0.3 Jira 연동의 핵심).
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import db
from gate import report_allowed
from onboarding import ONBOARDING_MESSAGE, contact_keyboard, form_keyboard
from validation import validate_report

logger = logging.getLogger("ixibot.reports")

SUMMARY_MAX = 50


def summarize(text: str) -> str:
    return text if len(text) <= SUMMARY_MAX else text[:SUMMARY_MAX] + "…"


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    sender = update.effective_user
    if message is None or sender is None or message.web_app_data is None:
        return

    # 1. 게이트 — 미승인이면 기록하지 않는다 (§4-3-1)
    user = await db.find_user_by_telegram_id(sender.id)
    if not report_allowed(user):
        logger.info("미승인 보고 차단 (tg_id=%s)", sender.id)
        await message.reply_text(
            "등록 확인 후 이용할 수 있습니다.\n\n" + ONBOARDING_MESSAGE,
            reply_markup=contact_keyboard(),
        )
        return

    # 2. 재검증 (validation.py) — 페이로드 원문은 로그에 남기지 않는다
    result = validate_report(message.web_app_data.data)
    if not result.ok:
        logger.warning("검증 실패 (tg_id=%s): %s", sender.id, result.error)
        await message.reply_text(
            "제출 내용에 문제가 있어 접수하지 못했습니다 ❌\n"
            f"사유: {result.error}\n\n"
            "아래 버튼을 눌러 다시 작성해 주세요.",
            reply_markup=form_keyboard(),
        )
        return

    # 3. 기록 — usr_id 귀속 (§3 reports)
    report = result.report
    report_id = await db.save_report(
        usr_id=user["usr_id"],
        telegram_user_id=sender.id,
        symptom_time=report["symptom_time"],
        symptom_time_ts=report["symptom_time_ts"],
        symptom_text=report["symptom_text"],
    )
    logger.info("보고 접수 (tg_id=%s, report_id=%s)", sender.id, report_id)

    # 실명 미표기 (§1-4)
    await message.reply_text(
        "접수되었습니다 ✅\n"
        f"🕐 {report['symptom_time']}\n"
        f"📝 {summarize(report['symptom_text'])}",
        reply_markup=form_keyboard(),
    )
