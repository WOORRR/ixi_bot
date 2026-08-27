"""phone.py 단위 테스트 — 네트워크·Firestore 불필요.

키는 테스트용 더미 값 (실제 시크릿 아님 — 지침서 §1-5).
"""

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phone import decrypt_tel, encrypt_tel, mask_tel, normalize_tel, tel_hmac

DUMMY_HASH_KEY = "unit-test-dummy-hash-key"
DUMMY_ENC_KEY = base64.b64encode(bytes(range(32))).decode("ascii")


@pytest.fixture(autouse=True)
def _dummy_keys(monkeypatch):
    monkeypatch.setenv("TEL_HASH_KEY", DUMMY_HASH_KEY)
    monkeypatch.setenv("TEL_ENC_KEY", DUMMY_ENC_KEY)


class TestNormalize:
    @pytest.mark.parametrize(
        "raw",
        [
            "010-1234-5678",
            "+821012345678",
            "821012345678",
            "01012345678",
            "+82 10-1234-5678",
        ],
    )
    def test_variants_converge(self, raw):
        assert normalize_tel(raw) == "+821012345678"

    def test_old_style_seven_digit_body(self):
        # 010-XXX-XXXX (7자리 본체)도 허용
        assert normalize_tel("010-123-4567") == "+82101234567"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "abc",
            "02-1234-5678",       # 지역번호 (휴대전화 아님)
            "010-1234",           # 자릿수 부족
            "010-1234-567890",    # 자릿수 초과
            "+12025550123",       # 해외 번호
            None,
        ],
    )
    def test_invalid_raises(self, raw):
        with pytest.raises(ValueError):
            normalize_tel(raw)


class TestHmac:
    def test_deterministic(self):
        assert tel_hmac("+821012345678") == tel_hmac("+821012345678")

    def test_different_numbers_differ(self):
        assert tel_hmac("+821012345678") != tel_hmac("+821012345679")

    def test_key_dependent(self, monkeypatch):
        h1 = tel_hmac("+821012345678")
        monkeypatch.setenv("TEL_HASH_KEY", "another-dummy-key")
        assert tel_hmac("+821012345678") != h1

    def test_hex_format(self):
        h = tel_hmac("+821012345678")
        assert len(h) == 64
        int(h, 16)  # hex 문자열이어야 한다


class TestEncrypt:
    def test_roundtrip(self):
        enc = encrypt_tel("+821012345678")
        assert decrypt_tel(enc) == "+821012345678"

    def test_nonce_randomized(self):
        # 같은 평문도 매번 다른 암호문 (nonce 무작위)
        assert encrypt_tel("+821012345678") != encrypt_tel("+821012345678")

    def test_ciphertext_no_plaintext(self):
        enc = encrypt_tel("+821012345678")
        assert "1234" not in enc and "5678" not in enc

    def test_blob_layout(self):
        blob = base64.b64decode(encrypt_tel("+821012345678"))
        # nonce 12B + ciphertext(13B) + GCM tag 16B
        assert len(blob) == 12 + 13 + 16

    def test_wrong_key_fails(self, monkeypatch):
        enc = encrypt_tel("+821012345678")
        monkeypatch.setenv(
            "TEL_ENC_KEY", base64.b64encode(bytes(range(1, 33))).decode("ascii")
        )
        with pytest.raises(Exception):
            decrypt_tel(enc)

    def test_bad_enc_key_length(self, monkeypatch):
        monkeypatch.setenv("TEL_ENC_KEY", base64.b64encode(b"short").decode("ascii"))
        with pytest.raises(RuntimeError):
            encrypt_tel("+821012345678")


class TestMask:
    def test_hyphen_form(self):
        assert mask_tel("010-1234-5678") == "010-****-5678"

    def test_e164_form(self):
        assert mask_tel("+821012345678") == "010-****-5678"

    def test_seven_digit_body(self):
        assert mask_tel("010-123-4567") == "010-***-4567"
