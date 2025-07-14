# Slack-Notion Calendar Connect

**Slack**에서 휴가 신청/취소 메시지를 읽어 **Notion 캘린더 데이터베이스**에 자동으로 반영하는 Python 스크립트

---

## 주요 기능

- Slack 채널에서 최근 휴가 관련 메시지(신청/취소) 자동 수집
- 메시지 패턴 분석(연차, 반차, 날짜 범위, 취소 등)
- Notion 캘린더 데이터베이스에 휴가 정보 자동 등록/삭제
- 중복 휴가 데이터 방지

---

## 사용 방법

### 1. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성하고 아래 항목을 입력하세요.

```env
SLACK_TOKEN=슬랙_봇_토큰
SLACK_CHANNEL_ID=휴가신청_채널_ID
NOTION_TOKEN=노션_통합_토큰
NOTION_DATABASE_ID=노션_캘린더_데이터베이스_ID
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```
또는 Poetry 사용 시:
```bash
poetry install
```

### 3. 실행

```bash
python slack_notion_callendar_connect.py
```

---

## Slack 메시지 템플릿

아래와 같은 형식의 메시지를 Slack에 입력하면 자동으로 인식됩니다.

- **하루종일 휴가:**  
  `홍길동 - 5월 10일 하루종일 휴가입니다.`
- **날짜 범위 휴가:**  
  `홍길동 - 5월 10일 ~ 5월 12일 휴가입니다.`
- **반차(오전/오후):**  
  `홍길동 - 5월 10일 오전`  
  `홍길동 - 5월 10일 오후`
- **휴가 취소:**  
  `홍길동 - 5월 10일 하루종일 휴가가 취소되었습니다.`

---

## Notion 데이터베이스 요구사항

- **Name** (title)
- **이름** (rich_text)
- **날짜** (date)
- **휴가유형** (select) : 연차/오후반차/오전반차