"""IxiBot v0.2 — 텔레그램 오류 증상 보고 수집 봇 (지침서 §4-5).

- WEBHOOK_URL 설정 시: Cloud Run webhook 모드 (PTB run_webhook 이 secret_token 검증까지 수행)
- 미설정 시: long polling (로컬 개발 폴백)

온보딩(연락처 자동 매칭/실명 폴백) → 승인 사용자만 Mini App 폼으로 보고 →
Firestore reports 에 usr_id 귀속 기록.
"""

import logging
import os
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import admin
import onboarding
import reports
from config import BOT_TOKEN, FORM_URL, WEBHOOK_SECRET, WEBHOOK_URL

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("ixibot")

# chat_member 가 빠지면 그룹 입장 감지가 조용히 실패한다 — 반드시 포함 (§4-5)
ALLOWED_UPDATES = ["message", "callback_query", "chat_member"]


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    private = filters.ChatType.PRIVATE

    app.add_handler(CommandHandler("start", onboarding.start, filters=private))
    app.add_handler(CommandHandler("pending", admin.cmd_pending))
    app.add_handler(CommandHandler("users", admin.cmd_users))
    app.add_handler(CommandHandler("revoke", admin.cmd_revoke))
    app.add_handler(CommandHandler("unbind", admin.cmd_unbind))
    app.add_handler(CommandHandler("whoami", admin.cmd_whoami))

    app.add_handler(ChatMemberHandler(onboarding.on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.CONTACT & private, onboarding.handle_contact))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, reports.handle_web_app_data)
    )
    # 실명 폴백 — join_requests.state == awaiting_name 일 때만 내부에서 반응
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & private, onboarding.handle_text)
    )
    app.add_handler(CallbackQueryHandler(admin.handle_callback))
    return app


def main() -> None:
    app = build_application()

    if WEBHOOK_URL:
        url_path = urlparse(WEBHOOK_URL).path.lstrip("/")
        logger.info("IxiBot webhook 모드 시작 — 폼 URL: %s", FORM_URL)
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
            url_path=url_path,
            secret_token=WEBHOOK_SECRET,
            webhook_url=WEBHOOK_URL,
            allowed_updates=ALLOWED_UPDATES,
        )
    else:
        logger.info("IxiBot polling 모드 시작 (로컬 개발) — 폼 URL: %s", FORM_URL)
        app.run_polling(allowed_updates=ALLOWED_UPDATES)


if __name__ == "__main__":
    main()
