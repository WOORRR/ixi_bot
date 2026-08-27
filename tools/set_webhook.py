"""텔레그램 webhook 등록/해제/확인 도구 (지침서 Phase 4).

사용법:
    python tools/set_webhook.py set     # WEBHOOK_URL + WEBHOOK_SECRET 로 등록
    python tools/set_webhook.py delete  # webhook 해제 (long polling 복귀용)
    python tools/set_webhook.py info    # getWebhookInfo 출력

.env 의 BOT_TOKEN·WEBHOOK_URL·WEBHOOK_SECRET 을 사용한다.
allowed_updates 에 chat_member 필수 — 빠지면 그룹 입장 감지가 조용히 실패한다 (§4-5).
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ALLOWED_UPDATES = ["message", "callback_query", "chat_member"]


def _api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) != 2 or sys.argv[1] not in ("set", "delete", "info"):
        raise SystemExit(__doc__)
    command = sys.argv[1]

    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN 이 설정되지 않았습니다 (.env 확인).")

    if command == "set":
        webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
        secret = os.environ.get("WEBHOOK_SECRET", "").strip()
        if not webhook_url or not secret:
            raise SystemExit("set 에는 WEBHOOK_URL 과 WEBHOOK_SECRET 이 모두 필요합니다.")
        result = _api(
            token,
            "setWebhook",
            {
                "url": webhook_url,
                "secret_token": secret,
                "allowed_updates": ALLOWED_UPDATES,
                "drop_pending_updates": False,
            },
        )
    elif command == "delete":
        result = _api(token, "deleteWebhook", {"drop_pending_updates": False})
    else:
        result = _api(token, "getWebhookInfo")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
