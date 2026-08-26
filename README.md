# IxiBot v0.1 — 텔레그램 오류 증상 보고 수집 봇

기획서: [ixibot_v0.1_기획서_3.md](ixibot_v0.1_기획서_3.md)

사용자가 겪은 서비스 오류 증상(누가 / 언제 / 어떤 증상)을 Telegram Mini App 폼으로 수집한다.
v0.1은 입력 UI 사용성 검증이 목표이며, 데이터는 `reports.jsonl` 파일에 임시 기록된다.

## 구조

```
├── main.py             # 봇 기동, /start·web_app_data 핸들러 (long polling)
├── config.py           # .env 로드 (BOT_TOKEN, FORM_URL)
├── names.py            # 이름 후보 86명 리스트 — 단일 소스 (⚠️ 현재 자리표시자)
├── validation.py       # 서버 측 재검증 (이름·시각·길이)
├── storage.py          # save_report() — v0.1: JSONL / v0.2: DB로 교체 예정
├── docs/index.html     # Mini App 폼 (GitHub Pages 배포 대상)
├── tools/sync_names.py # names.py → index.html JS 배열 동기화
└── tests/              # pytest 단위 테스트
```

## 실행 준비

1. **토큰 재발급 (필수)** — BotFather에서 `/revoke` → `@woorrr_ixi_bot` 선택 → 새 토큰 발급.
   (최초 토큰이 채팅에 평문 노출된 적이 있음 — 기획서 §1)

2. **이름 명단 교체** — `names.py`의 자리표시자 86명을 실제 명단으로 바꾼 뒤 동기화:

   ```bash
   python tools/sync_names.py
   ```

3. **폼 페이지 배포 (GitHub Pages)**
   - 이 저장소를 GitHub에 push (저장소는 비공개 가능, Pages만 공개됨)
   - 저장소 Settings → Pages → Branch: `main`, 폴더: `/docs` 선택
   - 발급된 주소(`https://<아이디>.github.io/<저장소>/`)를 `.env`의 `FORM_URL`에 기입

4. **.env 작성** — `.env.example`을 `.env`로 복사하고 실제 값 기입:

   ```
   BOT_TOKEN=재발급받은_토큰
   FORM_URL=https://<아이디>.github.io/<저장소>/
   ```

5. **의존성 설치**

   ```bash
   pip install -r requirements.txt
   ```

## 실행

```bash
python main.py
```

로컬 PC에서 long polling으로 동작한다 (서버 불필요). 텔레그램에서 `@woorrr_ixi_bot`에게
`/start`를 보내면 [📝 증상 보고하기] 버튼이 나타나고, 누르면 폼(Mini App)이 열린다.

그룹방 운영 시 핀 메시지에 딥링크 버튼을 사용: `https://t.me/woorrr_ixi_bot?start=report`

제출된 데이터는 `reports.jsonl`에 한 줄당 한 건씩 기록된다:

```json
{"telegram_user_id": 12345, "name": "김정민", "symptom_time": "2026-08-26 14:35", "symptom_text": "...", "submitted_at": "2026-08-26T14:36:02+09:00"}
```

## 테스트

```bash
python -m pytest tests/ -v
```

## 주의점 (기획서 §5)

- 폼을 여는 버튼은 반드시 **ReplyKeyboardMarkup의 web_app 버튼** — 인라인 버튼으로 열면 `sendData`가 봇에 전달되지 않음
- 이름 리스트는 `names.py`가 단일 소스 — 수정 후 반드시 `python tools/sync_names.py` 실행
- iOS / Android / 데스크톱에서 `datetime-local` UI가 다르므로 세 플랫폼 모두 확인할 것
