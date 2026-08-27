"""환경변수 로드 및 기동 전 검사 (지침서 §2-2).

문제가 있으면 한국어 안내 후 즉시 종료한다 (v0.1 방식 유지).
"""

import base64
import os
import re

from dotenv import load_dotenv

load_dotenv()

_errors: list[str] = []


def _require(name: str, hint: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        _errors.append(f"- {name}: {hint}")
    return value


BOT_TOKEN = _require("BOT_TOKEN", "BotFather에서 발급받은 봇 토큰을 넣어주세요.")
if BOT_TOKEN == "여기에_재발급받은_토큰":
    _errors.append("- BOT_TOKEN: 예시 값 그대로입니다. 실제 토큰으로 바꿔주세요.")

FORM_URL = _require(
    "FORM_URL", "Mini App 폼 주소(HTTPS)를 넣어주세요. 예: https://woorrr.github.io/ixi_bot/"
)
if FORM_URL and not FORM_URL.startswith("https://"):
    _errors.append("- FORM_URL: https:// 로 시작해야 합니다 (텔레그램 Mini App 요건).")

TEL_HASH_KEY = _require(
    "TEL_HASH_KEY", "전화번호 HMAC 키가 없습니다. `openssl rand -base64 32` 로 생성하세요."
)

TEL_ENC_KEY = _require(
    "TEL_ENC_KEY",
    "전화번호 암호화 키가 없습니다. `openssl rand -base64 32` 로 생성하세요 (HMAC 키와 다른 값).",
)
if TEL_ENC_KEY:
    try:
        if len(base64.b64decode(TEL_ENC_KEY, validate=True)) != 32:
            raise ValueError
    except Exception:
        _errors.append("- TEL_ENC_KEY: base64 인코딩된 32바이트 키여야 합니다.")
    if TEL_ENC_KEY == TEL_HASH_KEY:
        _errors.append("- TEL_ENC_KEY: TEL_HASH_KEY 와 다른 값이어야 합니다.")

_admin_raw = _require("ADMIN_CHAT_ID", "관리자 1:1 chat ID(정수)를 넣어주세요. 봇에 /whoami 로 확인.")
ADMIN_CHAT_ID = 0
if _admin_raw:
    try:
        ADMIN_CHAT_ID = int(_admin_raw)
    except ValueError:
        _errors.append("- ADMIN_CHAT_ID: 정수여야 합니다.")

_group_raw = _require(
    "GROUP_CHAT_ID", "운영 대상 그룹방 ID(음수 정수)를 넣어주세요. 그룹에서 /whoami 로 확인."
)
GROUP_CHAT_ID = 0
if _group_raw:
    try:
        GROUP_CHAT_ID = int(_group_raw)
        if GROUP_CHAT_ID >= 0:
            _errors.append("- GROUP_CHAT_ID: 그룹방 ID는 음수 정수입니다.")
    except ValueError:
        _errors.append("- GROUP_CHAT_ID: 정수여야 합니다.")

# webhook 은 선택 — 미설정이면 long polling 으로 기동 (로컬 개발 폴백)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
if WEBHOOK_URL:
    if not WEBHOOK_URL.startswith("https://"):
        _errors.append("- WEBHOOK_URL: https:// 로 시작해야 합니다.")
    if not WEBHOOK_SECRET:
        _errors.append("- WEBHOOK_SECRET: WEBHOOK_URL 설정 시 필수입니다 (수신 헤더 검증값).")
    elif not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", WEBHOOK_SECRET):
        _errors.append(
            "- WEBHOOK_SECRET: 텔레그램 secret_token 은 영숫자·'_'·'-' 만 허용합니다 "
            "(base64 의 +/= 불가 — `openssl rand -hex 32` 등으로 재생성)."
        )

if _errors:
    raise SystemExit(
        ".env 설정에 문제가 있습니다:\n"
        + "\n".join(_errors)
        + "\n\n.env.example 을 참고해 .env 를 채워주세요."
    )
