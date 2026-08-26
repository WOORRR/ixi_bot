"""환경변수 로드 및 설정 상수."""

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN or BOT_TOKEN == "여기에_재발급받은_토큰":
    raise SystemExit(
        ".env 파일에 BOT_TOKEN이 설정되지 않았습니다.\n"
        ".env.example 을 .env 로 복사한 뒤, BotFather에서 재발급받은 토큰을 넣어주세요."
    )

FORM_URL = os.environ.get("FORM_URL", "").strip()
if not FORM_URL or not FORM_URL.startswith("https://"):
    raise SystemExit(
        ".env 파일에 FORM_URL(HTTPS 폼 주소)이 설정되지 않았습니다.\n"
        "GitHub Pages에 docs/index.html 을 배포한 뒤 그 주소를 넣어주세요.\n"
        "예: FORM_URL=https://<깃허브아이디>.github.io/<저장소이름>/"
    )
