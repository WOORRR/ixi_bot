# IxiBot v0.2 — 텔레그램 오류 증상 보고 수집 봇

사용자가 겪은 서비스 오류 증상(언제 / 어떤 증상)을 Telegram Mini App 폼으로 수집한다.

v0.2 핵심 변경:

- 폼에서 **이름 입력 제거** — 제출자는 온보딩 시 바인딩된 `telegram_user_id → usr_id`로 귀속
- **Firestore** 도입 (명단 + 보고 기록), JSONL 폐기
- **Cloud Run + webhook** 상시 운영 (`WEBHOOK_URL` 미설정 시 long polling — 로컬 개발 폴백)
- **온보딩**: 연락처 공유 → 전화번호 HMAC 자동 매칭 선승인 + 관리자 후심사, 불일치 시 실명 문의 → 수작업 승인
- **미승인 사용자 보고 차단**, 전화번호는 AES-256-GCM 암호문·HMAC·마스킹만 저장 (평문 없음)

## 구조

```
├── main.py             # 기동: 핸들러 등록, webhook/polling 분기
├── config.py           # .env 로드 + 기동 전 검사
├── phone.py            # 전화번호 정규화·HMAC·암호화·마스킹
├── gate.py             # 승인/거부 판정 (순수 함수 — Firestore 불필요)
├── db.py               # Firestore 데이터 계층 (클라이언트는 이 모듈에만)
├── onboarding.py       # 그룹 입장 감지, /start, 연락처/실명 온보딩
├── admin.py            # 관리자 콜백·명령 (/pending /users /revoke /unbind /whoami)
├── reports.py          # web_app_data 게이트·검증·기록
├── validation.py       # 보고 페이로드 서버 측 재검증
├── docs/index.html     # Mini App 폼 (GitHub Pages 배포 대상, 시각+증상 2항목)
├── tools/seed_users.py # user_list_Sql.txt → Firestore users 시드
├── tools/set_webhook.py# webhook set/delete/info
├── firestore.rules     # 전면 차단 규칙 (클라이언트 SDK 미사용)
├── Dockerfile          # Cloud Run 배포용
└── tests/              # pytest — 네트워크·Firestore 없이 실행 가능
```

## 로컬 실행

1. **의존성 설치**

   ```bash
   pip install -r requirements.txt
   ```

2. **.env 작성** — `.env.example`을 `.env`로 복사하고 값 기입.
   `TEL_HASH_KEY`·`TEL_ENC_KEY`는 `openssl rand -base64 32`로 각각 생성(서로 다른 값).
   `ADMIN_CHAT_ID`·`GROUP_CHAT_ID`는 봇 기동 후 `/whoami`로 확인해 채운다.

3. **Firestore 접근 (로컬)** — 서비스 계정 키 파일 경로를
   `GOOGLE_APPLICATION_CREDENTIALS`에 지정한다. 키 파일은 `.gitignore` 대상
   (`*.serviceaccount.json`)으로 두고 절대 커밋하지 않는다.

4. **기동**

   ```bash
   python main.py
   ```

   `WEBHOOK_URL`이 없으면 long polling으로 동작한다 (서버 불필요).

## 시드 (users 적재)

1. 로컬의 `user_list_Sql.txt`(**커밋 금지** — .gitignore 등록됨) 끝에 관리자 행 1줄을
   이어 붙인다 (운영자 절차 §5 참조). 합계 **81행**(명단 80 + 관리자 1)이어야 한다.
2. 실행:

   ```bash
   python tools/seed_users.py
   ```

   - 81건·중복 없음 검증 후 적재. 이미 있는 문서는 건너뜀 (재실행 안전).
   - 적재 후 임의 1건 암복호 self-check. 출력에 평문 전화번호는 찍히지 않는다.

## 폼 페이지 배포 (GitHub Pages)

- 저장소 Settings → Pages → Branch: `main`, 폴더: `/docs`
- 발급 주소(`https://woorrr.github.io/ixi_bot/`)를 `.env`/Cloud Run의 `FORM_URL`에 기입

## Cloud Run 배포

운영자 수작업 절차(아래 §운영자 절차)를 먼저 완료한 뒤:

```bash
gcloud run deploy ixibot --source . --region asia-northeast3 \
  --min-instances 0 --max-instances 1 --allow-unauthenticated \
  --service-account ixibot-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --set-secrets BOT_TOKEN=BOT_TOKEN:latest,WEBHOOK_SECRET=WEBHOOK_SECRET:latest,TEL_HASH_KEY=TEL_HASH_KEY:latest,TEL_ENC_KEY=TEL_ENC_KEY:latest \
  --set-env-vars WEBHOOK_URL=https://ixibot-xxxx.run.app/webhook/<랜덤문자열>,ADMIN_CHAT_ID=<정수>,GROUP_CHAT_ID=<음수정수>,FORM_URL=https://woorrr.github.io/ixi_bot/
```

- `--max-instances 1` 필수 (인스턴스 단일 전제).
- 최초 배포 후 실제 서비스 URL을 확인해 `WEBHOOK_URL`을 갱신·재배포한다.

## webhook 등록

```bash
python tools/set_webhook.py set
```

```bash
python tools/set_webhook.py info
```

`info`로 등록 상태를 확인한다. `allowed_updates`에 `chat_member`가 포함되어야
그룹 입장 감지가 동작한다 (set 서브커맨드가 자동 포함).
로컬 polling으로 돌아가려면 `python tools/set_webhook.py delete`.

## Firestore 보안 규칙 적용

클라이언트 SDK를 쓰지 않으므로 전면 차단 규칙을 적용한다:

- Firebase Console → Firestore → 규칙에 `firestore.rules` 내용 붙여넣기 → 게시
- 또는 Firebase CLI: `firebase deploy --only firestore:rules`

## 테스트

```bash
python -m pytest tests/ -v
```

네트워크·Firestore 없이 전부 통과해야 한다.

## 운영자 절차 (수작업 — 지침서 §8 요약)

1. GCP 프로젝트 생성 + 결제 연결, API 활성화 (Cloud Run, Cloud Build, Firestore, Secret Manager)
2. Firestore 데이터베이스 생성 (**Native mode, asia-northeast3**) + `firestore.rules` 적용
3. Secret Manager에 `BOT_TOKEN`·`WEBHOOK_SECRET`·`TEL_HASH_KEY`·`TEL_ENC_KEY` 등록
   (키 2개는 `openssl rand -base64 32`로 생성)
4. 서비스 계정 생성 (`roles/datastore.user`, `roles/secretmanager.secretAccessor`) +
   로컬 시드용 키 발급 (키 파일은 로컬에만)
5. `user_list_Sql.txt` 끝에 관리자 행 추가 → `python tools/seed_users.py` (81건 적재 확인)
6. 위 `gcloud run deploy` 명령으로 배포
7. `python tools/set_webhook.py set` → `info`로 확인
8. 텔레그램: 그룹방 생성 → 봇을 **관리자로** 추가 → `/whoami`로 `ADMIN_CHAT_ID`(1:1)·
   `GROUP_CHAT_ID`(그룹) 확인 → 핀 메시지(딥링크 버튼 `https://t.me/woorrr_ixi_bot?start=verify`) 게시
9. 실사용 검증: 온보딩(자동 승인/폴백/차단)·보고 제출·`/revoke`·`/unbind` 각 1회 이상

## 주의점

- 폼을 여는 버튼은 반드시 **ReplyKeyboardMarkup의 web_app 버튼** — 인라인 버튼으로 열면
  `sendData`가 봇에 전달되지 않음
- `user_list_Sql.txt`·`.env`·서비스 계정 키·기획서/지침서 문서는 **절대 커밋 금지**
  (`.gitignore` 등록됨 — 저장소는 공개)
- 전화번호 평문은 DB·로그·메시지 어디에도 남기지 않는다. 관리자 표시는 마스킹
  (`010-****-5678`)만 사용
- iOS / Android / 데스크톱에서 `datetime-local` UI가 다르므로 세 플랫폼 모두 확인할 것
- 텔레그램은 Mini App 페이지를 오래 캐시한다 — 폼 수정 배포 후에는 `FORM_URL`에
  버전 파라미터(`?v=2` → `?v=3` …)를 올려 Cloud Run 환경변수를 갱신하고, 사용자는
  `/start`로 새 키보드 버튼을 받아야 반영된다 (버튼에 URL이 박혀 있음)
