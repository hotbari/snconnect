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
# NOTION_URL = "https://www.notion.so/1337f93d4eff80fda960dee9d56fe0df?v=d1114e0a70fa4659b13d31b3b01e2872&pvs=4"

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

# 메시지 패턴 설정 (예: "휴가 신청: 이름, 날짜, 유형")
message_pattern = re.compile(r"휴가 신청:\s*(\S+),\s*(\d{4}-\d{2}-\d{2}),\s*(\S+)")

def parse_message(message):
    """메시지에서 휴가 신청 정보 추출"""
    match = message_pattern.search(message)
    if match:
        return {
            "name": match.group(1),
            "date": match.group(2),
            "type": match.group(3)
        }
    return None

NOTION_URL = "https://api.notion.com/v1/pages"
NOTION_SEARCH_URL = "https://api.notion.com/v1/databases/{}/query"

def check_duplicate_date(vacation_date):
    """중복 날짜 검사"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2021-08-16"
    }
    query = {
        "filter": {
            "property": "날짜",  # 날짜 속성의 실제 이름
            "date": {
                "equals": vacation_date
            }
        }
    }
    response = requests.post(NOTION_SEARCH_URL.format(NOTION_DATABASE_ID), headers=headers, json=query)
    
    if response.status_code == 200:
        results = response.json().get("results", [])
        return len(results) > 0  # 결과가 있으면 중복
    else:
        print(f"Failed to check duplicates: {response.status_code}, {response.text}")
        return False


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
            if not check_duplicate_date(vacation_info["date"]):
                add_to_notion_calendar(vacation_info)
            else:
                print(f"중복 데이터가 발견되었습니다: {vacation_info['date']}")
                
if __name__ == "__main__":
    main()
