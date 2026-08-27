"""전화번호 정규화·해시·암호화·마스킹 (지침서 §4-1).

- 평문 전화번호는 DB·로그·메시지 어디에도 남기지 않는다 (§1-2).
- decrypt_tel() 의 호출처는 시드 스크립트 self-check 와 단위 테스트뿐이다 (§1-3).
- 키는 환경변수에서 호출 시점에 읽는다 (임포트 시 환경 요구 없음 — 테스트 용이).
"""

import base64
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 한국 휴대전화: "8210" + 7~8자리 (010-XXX-XXXX / 010-XXXX-XXXX)
_VALID_DIGIT_LENGTHS = (11, 12)


def _hash_key() -> bytes:
    key = os.environ.get("TEL_HASH_KEY", "").strip()
    if not key:
        raise RuntimeError("TEL_HASH_KEY 환경변수가 설정되지 않았습니다")
    return key.encode("utf-8")


def _enc_key() -> bytes:
    raw = os.environ.get("TEL_ENC_KEY", "").strip()
    if not raw:
        raise RuntimeError("TEL_ENC_KEY 환경변수가 설정되지 않았습니다")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError("TEL_ENC_KEY 는 base64 문자열이어야 합니다") from exc
    if len(key) != 32:
        raise RuntimeError("TEL_ENC_KEY 는 base64 디코드 시 32바이트여야 합니다")
    return key


def normalize_tel(raw: str) -> str:
    """"010-1234-5678" / "+821012345678" / "821012345678" → "+821012345678".

    규칙: 숫자만 추출 → "0"으로 시작하면 "82"+뒤 → 선두 "+" 부여.
    한국 휴대전화 범위("+8210" 시작, 11~12자리)가 아니면 ValueError.
    """
    if not isinstance(raw, str):
        raise ValueError("전화번호 형식이 올바르지 않습니다")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise ValueError("전화번호 형식이 올바르지 않습니다")
    if digits.startswith("0"):
        digits = "82" + digits[1:]
    e164 = "+" + digits
    if not e164.startswith("+8210") or len(digits) not in _VALID_DIGIT_LENGTHS:
        raise ValueError("한국 휴대전화 번호 형식이 아닙니다")
    return e164


def tel_hmac(e164: str) -> str:
    """HMAC-SHA256(TEL_HASH_KEY, e164) → hex."""
    return hmac.new(_hash_key(), e164.encode("utf-8"), hashlib.sha256).hexdigest()


def encrypt_tel(e164: str) -> str:
    """AES-256-GCM 암호화 → base64( nonce(12B) + ciphertext+tag )."""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_enc_key()).encrypt(nonce, e164.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_tel(enc: str) -> str:
    """encrypt_tel 의 역변환.

    ⚠️ 호출처 제한(§1-3): 시드 스크립트 self-check 와 단위 테스트에서만 호출한다.
    실사용 복호화는 v0.3 Jira 연동에서 시작한다.
    """
    blob = base64.b64decode(enc)
    nonce, ciphertext = blob[:12], blob[12:]
    return AESGCM(_enc_key()).decrypt(nonce, ciphertext, None).decode("utf-8")


def mask_tel(raw: str) -> str:
    """"010-1234-5678" → "010-****-5678" (하이픈 형식 기준)."""
    e164 = normalize_tel(raw)
    local = "0" + e164[3:]  # "+82" 제거 후 국내 형식으로
    middle = local[3:-4]
    return f"{local[:3]}-{'*' * len(middle)}-{local[-4:]}"
