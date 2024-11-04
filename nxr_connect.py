import os
import re
import requests
# ssl 인증서 문제 해결
import ssl
import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# .env 파일에서 환경 변수 로드
load_dotenv()

# 환경 변수 가져오기
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
NOTION_URL = "https://api.notion.com/v1/pages"

# SSL 인증서 문제 해결
ssl_context = ssl.create_default_context(cafile=certifi.where())
slack_client = WebClient(token=SLACK_TOKEN, ssl=ssl_context)  # SSL 컨텍스트 설정

def get_recent_messages():
    """특정 슬랙 채널에서 최근 메시지 가져오기"""
    try:
        response = slack_client.conversations_history(channel=SLACK_CHANNEL_ID, limit=10)
        messages = response.get("messages", [])
        return messages
    except SlackApiError as e:
        print(f"Error fetching messages: {e.response['error']}")
        return []

# 메시지 패턴 설정
message_pattern = re.compile(
    r"\[(?P<name>.+?)\]\s*-\s*(?P<dates>(\d{4}-\d{2}-\d{2}|\d{1,2}월\s*\d{1,2}일)(\s*~\s*(\d{4}-\d{2}-\d{2}|\d{1,2}월\s*\d{1,2}일))?)\s*(?P<time>(오전|오후)?\s*\d{1,2}:\d{2}\s*~\s*(오전|오후)?\s*\d{1,2}:\d{2})?\s*(휴가가\s*취소되었습니다.|휴가입니다.)"
)

def parse_message(message):
    """메시지에서 휴가 신청 정보 추출"""
    match = message_pattern.search(message)
    if match:
        name = match.group("name").strip()
        date_info = match.group("dates").strip()
        
        # 날짜 형식 통일
        if "일" in date_info:
            # "10월 24일" 같은 형식 변환
            date_info = re.sub(r"(\d{1,2})월\s*(\d{1,2})일", lambda m: f"2024-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}", date_info)

        return {
            "name": name,
            "date": date_info,
            "type": "휴가" if "휴가입니다." in message else "취소"
        }
    return None

def add_to_notion_calendar(vacation_info):
    """노션 캘린더에 휴가 정보 추가"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2021-08-16"
    }

    title = f"[{vacation_info['type']}] {vacation_info['name']}"
    data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {  # 데이터베이스에서 실제 제목 속성의 이름
                "title": [{"text": {"content": title}}]
            },
            "이름": {
                "rich_text": [{"text": {"content": vacation_info["name"]}}]
            },
            "날짜": {
                "date": {"start": vacation_info["date"]}
            },
            "휴가유형": {
                "select": {"name": vacation_info["type"]}
            }
        }
    }

    response = requests.post(NOTION_URL, headers=headers, json=data)
    if response.status_code == 200:
        print("Notion 캘린더에 추가되었습니다.")
    else:
        print(f"Failed to add to Notion: {response.status_code}, {response.text}")

def main():
    messages = get_recent_messages()
    for msg in messages:
        text = msg.get("text", "")
        vacation_info = parse_message(text)
        if vacation_info:
            # 중복 체크 로직 추가
            if vacation_info["type"] == "휴가":
                # 여기서 중복 여부 확인 (날짜 기준)
                if not check_duplicate(vacation_info["date"]):
                    add_to_notion_calendar(vacation_info)

if __name__ == "__main__":
    main()
