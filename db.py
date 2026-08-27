"""Firestore 데이터 계층 (지침서 §3, Phase 3).

Firestore 클라이언트는 이 모듈에만 존재한다.
- 봇 런타임: AsyncClient (PTB 핸들러가 이벤트 루프를 막지 않도록)
- 시드 스크립트: sync Client (seed_* 함수)
승인/거부 판정은 gate.py(순수 함수)에 있고, 여기는 조회·쓰기만 담당한다.

트랜잭션 (§7-3): 바인딩·차단·해제·후심사 종결은 현재 상태를 재확인 후 쓴다.
중복 클릭·webhook 재전송이 와도 두 번째 실행은 "이미 처리됨"으로 끝난다 (멱등).
"""

from google.cloud import firestore

USERS = "users"
JOIN_REQUESTS = "join_requests"
REPORTS = "reports"

_async_client: firestore.AsyncClient | None = None


def _client() -> firestore.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = firestore.AsyncClient()
    return _async_client


def _with_id(snap) -> dict:
    doc = snap.to_dict()
    doc["usr_id"] = snap.id
    return doc


# ── users 조회 ──────────────────────────────────────────────


async def find_user_by_tel_hmac(tel_hmac: str) -> dict | None:
    query = _client().collection(USERS).where(
        filter=firestore.FieldFilter("usr_tel_hmac", "==", tel_hmac)
    ).limit(1)
    async for snap in query.stream():
        return _with_id(snap)
    return None


async def find_user_by_telegram_id(telegram_user_id: int) -> dict | None:
    query = _client().collection(USERS).where(
        filter=firestore.FieldFilter("telegram_user_id", "==", telegram_user_id)
    ).limit(1)
    async for snap in query.stream():
        return _with_id(snap)
    return None


async def get_user(usr_id: str) -> dict | None:
    snap = await _client().collection(USERS).document(usr_id).get()
    return _with_id(snap) if snap.exists else None


async def find_unbound_users_by_name(usr_nm: str) -> list[dict]:
    """실명 완전 일치 + status=='unbound' 인 후보들 (§4-2 텍스트 핸들러)."""
    query = _client().collection(USERS).where(
        filter=firestore.FieldFilter("usr_nm", "==", usr_nm)
    ).where(filter=firestore.FieldFilter("status", "==", "unbound"))
    return [_with_id(s) async for s in query.stream()]


async def count_users_by_status() -> dict[str, int]:
    counts = {"approved": 0, "unbound": 0, "revoked": 0}
    async for snap in _client().collection(USERS).stream():
        status = (snap.to_dict() or {}).get("status")
        if status in counts:
            counts[status] += 1
    return counts


async def list_needs_review_users() -> list[dict]:
    query = _client().collection(USERS).where(
        filter=firestore.FieldFilter("needs_review", "==", True)
    )
    return [_with_id(s) async for s in query.stream()]


async def list_bound_users() -> list[dict]:
    """telegram_user_id 가 바인딩된 사용자 (approved + revoked) — /revoke·/unbind 대상.

    Firestore 는 null 부등 조회를 지원하지 않으므로 status 로 조회 후 걸러낸다.
    """
    query = _client().collection(USERS).where(
        filter=firestore.FieldFilter("status", "in", ["approved", "revoked"])
    )
    return [
        _with_id(s)
        async for s in query.stream()
        if (s.to_dict() or {}).get("telegram_user_id") is not None
    ]


# ── users 상태 전이 (트랜잭션) ────────────────────────────────


async def bind_user(
    usr_id: str,
    telegram_user_id: int,
    telegram_username: str | None,
    approval_method: str,
) -> bool:
    """unbound → approved 바인딩. 이미 바인딩·비 unbound 상태면 False (멱등)."""
    client = _client()
    ref = client.collection(USERS).document(usr_id)

    @firestore.async_transactional
    async def _txn(transaction) -> bool:
        snap = await ref.get(transaction=transaction)
        doc = snap.to_dict() if snap.exists else None
        if (
            doc is None
            or doc.get("status") != "unbound"
            or doc.get("telegram_user_id") is not None
        ):
            return False
        transaction.update(
            ref,
            {
                "telegram_user_id": telegram_user_id,
                "telegram_username": telegram_username,
                "status": "approved",
                "approval_method": approval_method,
                "needs_review": approval_method == "phone_auto",
                "approved_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        return True

    return await _txn(client.transaction())


async def revoke_user(usr_id: str) -> bool:
    """approved → revoked. 이미 revoked 면 False."""
    client = _client()
    ref = client.collection(USERS).document(usr_id)

    @firestore.async_transactional
    async def _txn(transaction) -> bool:
        snap = await ref.get(transaction=transaction)
        doc = snap.to_dict() if snap.exists else None
        if doc is None or doc.get("status") != "approved":
            return False
        transaction.update(
            ref,
            {
                "status": "revoked",
                "needs_review": False,
                "revoked_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        return True

    return await _txn(client.transaction())


async def unbind_user(usr_id: str) -> bool:
    """바인딩 해제 → 재온보딩 가능 상태로 초기화. 이미 unbound 면 False."""
    client = _client()
    ref = client.collection(USERS).document(usr_id)

    @firestore.async_transactional
    async def _txn(transaction) -> bool:
        snap = await ref.get(transaction=transaction)
        doc = snap.to_dict() if snap.exists else None
        if doc is None or doc.get("telegram_user_id") is None:
            return False
        transaction.update(
            ref,
            {
                "telegram_user_id": None,
                "telegram_username": None,
                "status": "unbound",
                "approval_method": None,
                "needs_review": False,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        return True

    return await _txn(client.transaction())


async def set_review_done(usr_id: str) -> bool:
    """후심사 종결 (needs_review → False). 이미 종결이면 False."""
    client = _client()
    ref = client.collection(USERS).document(usr_id)

    @firestore.async_transactional
    async def _txn(transaction) -> bool:
        snap = await ref.get(transaction=transaction)
        doc = snap.to_dict() if snap.exists else None
        if doc is None or not doc.get("needs_review"):
            return False
        transaction.update(
            ref,
            {"needs_review": False, "updated_at": firestore.SERVER_TIMESTAMP},
        )
        return True

    return await _txn(client.transaction())


# ── join_requests (폴백 경로) ────────────────────────────────


async def get_join_request(telegram_user_id: int) -> dict | None:
    snap = (
        await _client().collection(JOIN_REQUESTS).document(str(telegram_user_id)).get()
    )
    return snap.to_dict() if snap.exists else None


async def upsert_join_request(telegram_user_id: int, fields: dict) -> None:
    ref = _client().collection(JOIN_REQUESTS).document(str(telegram_user_id))
    snap = await ref.get()
    if not snap.exists:
        fields = {"created_at": firestore.SERVER_TIMESTAMP, **fields}
    await ref.set(fields, merge=True)


async def list_pending_join_requests() -> list[dict]:
    query = _client().collection(JOIN_REQUESTS).where(
        filter=firestore.FieldFilter("state", "==", "pending")
    )
    out = []
    async for snap in query.stream():
        doc = snap.to_dict()
        doc["telegram_user_id"] = int(snap.id)
        out.append(doc)
    return out


async def approve_join_request(
    telegram_user_id: int, usr_id: str, telegram_username: str | None
) -> str:
    """수작업 승인 (jr_ap 콜백). users 바인딩 + join_requests 종결을 한 트랜잭션으로.

    반환: "ok" | "already"(jr 이미 종결) | "user_taken"(users 가 더 이상 unbound 아님)
    """
    client = _client()
    user_ref = client.collection(USERS).document(usr_id)
    jr_ref = client.collection(JOIN_REQUESTS).document(str(telegram_user_id))

    @firestore.async_transactional
    async def _txn(transaction) -> str:
        user_snap = await user_ref.get(transaction=transaction)
        jr_snap = await jr_ref.get(transaction=transaction)
        jr = jr_snap.to_dict() if jr_snap.exists else None
        if jr is None or jr.get("state") != "pending":
            return "already"
        user = user_snap.to_dict() if user_snap.exists else None
        if (
            user is None
            or user.get("status") != "unbound"
            or user.get("telegram_user_id") is not None
        ):
            return "user_taken"
        transaction.update(
            user_ref,
            {
                "telegram_user_id": telegram_user_id,
                "telegram_username": telegram_username,
                "status": "approved",
                "approval_method": "admin_manual",
                "needs_review": False,
                "approved_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
        transaction.update(
            jr_ref,
            {"state": "approved", "decided_at": firestore.SERVER_TIMESTAMP},
        )
        return "ok"

    return await _txn(client.transaction())


async def reject_join_request(telegram_user_id: int) -> bool:
    """수작업 거절 (jr_rej 콜백). pending 이 아니면 False."""
    client = _client()
    ref = client.collection(JOIN_REQUESTS).document(str(telegram_user_id))

    @firestore.async_transactional
    async def _txn(transaction) -> bool:
        snap = await ref.get(transaction=transaction)
        doc = snap.to_dict() if snap.exists else None
        if doc is None or doc.get("state") != "pending":
            return False
        transaction.update(
            ref, {"state": "rejected", "decided_at": firestore.SERVER_TIMESTAMP}
        )
        return True

    return await _txn(client.transaction())


# ── reports ─────────────────────────────────────────────────


async def save_report(
    usr_id: str,
    telegram_user_id: int,
    symptom_time: str,
    symptom_time_ts,
    symptom_text: str,
) -> str:
    """검증 통과한 보고 1건 기록. 문서 ID 반환."""
    _, ref = await _client().collection(REPORTS).add(
        {
            "usr_id": usr_id,
            "telegram_user_id": telegram_user_id,
            "symptom_time": symptom_time,
            "symptom_time_ts": symptom_time_ts,
            "symptom_text": symptom_text,
            "submitted_at": firestore.SERVER_TIMESTAMP,
            "jira_issue_key": None,  # v0.3 예약 (§3 reports)
        }
    )
    return ref.id


# ── 시드 전용 (sync — tools/seed_users.py 에서만 사용) ────────


def seed_upsert_users(records: list[dict]) -> dict[str, int]:
    """시드 적재. 이미 존재하는 문서는 건너뛴다 (재실행 안전 — Phase 4).

    records: [{usr_id, usr_nm, usr_tel_enc, usr_tel_hmac, usr_tel_masked}, ...]
    반환: {"created": n, "skipped": n}
    """
    client = firestore.Client()
    created = skipped = 0
    for rec in records:
        ref = client.collection(USERS).document(rec["usr_id"])
        if ref.get().exists:
            skipped += 1
            continue
        ref.set(
            {
                "usr_nm": rec["usr_nm"],
                "usr_tel_enc": rec["usr_tel_enc"],
                "usr_tel_hmac": rec["usr_tel_hmac"],
                "usr_tel_masked": rec["usr_tel_masked"],
                "telegram_user_id": None,
                "telegram_username": None,
                "status": "unbound",
                "approval_method": None,
                "needs_review": False,
                "approved_at": None,
                "revoked_at": None,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        )
        created += 1
    return {"created": created, "skipped": skipped}


def seed_get_user_enc(usr_id: str) -> str | None:
    """시드 self-check 용: 적재된 문서의 usr_tel_enc 를 읽는다 (sync)."""
    snap = firestore.Client().collection(USERS).document(usr_id).get()
    return (snap.to_dict() or {}).get("usr_tel_enc") if snap.exists else None
