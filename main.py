"""IxiBot v0.1 — 텔레그램 오류 증상 보고 수집 봇 (long polling).

/start (또는 딥링크 t.me/woorrr_ixi_bot?start=report)
  → [📝 증상 보고하기] 키보드 버튼 (Mini App 폼 열기)
  → 폼 제출(web_app_data) 수신 → 서버 측 재검증 → JSONL 기록 → 확인 메시지
"""

import logging

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, FORM_URL
from storage import save_report
from validation import validate_report

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
# httpx의 polling 요청 로그는 너무 시끄러우므로 낮춘다
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("ixibot")


def form_keyboard() -> ReplyKeyboardMarkup:
    """Mini App 폼을 여는 키보드 버튼.

    주의: sendData는 ReplyKeyboardMarkup의 web_app 버튼으로 열었을 때만
    봇에 전달된다 (인라인 버튼 사용 금지 — 기획서 §5 주의점).
    """
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📝 증상 보고하기", web_app=WebAppInfo(url=FORM_URL))]],
        resize_keyboard=True,
        is_persistent=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "안녕하세요, IxiBot입니다 🙂\n"
        "서비스 이용 중 겪은 오류 증상을 수집하고 있어요.\n\n"
        "아래 [📝 증상 보고하기] 버튼을 누르면 보고 폼이 열립니다.\n"
        "여러 번 제출하셔도 됩니다.",
        reply_markup=form_keyboard(),
    )


async def handle_web_app_data(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    user = update.effective_user
    raw = message.web_app_data.data
    logger.info("web_app_data 수신 (user_id=%s): %s", user.id if user else "?", raw)

    result = validate_report(raw)
    if not result.ok:
        logger.warning("검증 실패 (user_id=%s): %s", user.id if user else "?", result.error)
        await message.reply_text(
            f"제출 내용에 문제가 있어 접수하지 못했습니다 ❌\n"
            f"사유: {result.error}\n\n"
            "아래 버튼을 눌러 다시 작성해 주세요.",
            reply_markup=form_keyboard(),
        )
        return

    report = result.report
    save_report(report, telegram_user_id=user.id if user else None)
    await message.reply_text(
        "접수되었습니다 ✅\n"
        f"👤 {report['name']} / 🕐 {report['symptom_time']}\n"
        f"📝 {report['symptom_text']}",
        reply_markup=form_keyboard(),
    )


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data)
    )
    logger.info("IxiBot polling 시작 — 폼 URL: %s", FORM_URL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
