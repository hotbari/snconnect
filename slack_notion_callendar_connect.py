import os
import re
import requests
import ssl
import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, timedelta

load_dotenv()

# 환경 변수 로드
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

# SSL 컨텍스트 설정
ssl_context = ssl.create_default_context(cafile=certifi.where())
slack_client = WebClient(token=SLACK_TOKEN, ssl=ssl_context)

def get_recent_messages():
    """Slack에서 최근 메시지를 가져옵니다."""
    try:
        response = slack_client.conversations_history(channel=SLACK_CHANNEL_ID, limit=10)
        return response.get("messages", [])
    except SlackApiError as e:
        print(f"Error fetching messages: {e.response['error']}")
        return []

def convert_to_iso_date(date_str):
    """월/일 형식의 날짜 문자열을 ISO 8601 형식으로 변환"""
    try:
        # 월/일 형식이 아닌 경우
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            return date_str
        
        # 현재 연도 가져오기
        current_year = datetime.now().year

        # 월/일 형식 변환
        date_with_year_str = f"{current_year}년 {date_str}"
        date_obj = datetime.strptime(date_with_year_str, "%Y년 %m월 %d일")
        return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        print(f"잘못된 날짜 형식입니다: {date_str}")
        return None

def parse_message(message):
    """
    슬랙 메시지에서 휴가 신청 정보 추출
    """
    if "취소되었습니다" in message:
        # 취소된 경우
        return {"type": "cancel", "message": message}

    # 하루종일 패턴
    all_day_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) 하루종일 휴가입니다.")
    
    # 날짜 범위 패턴
    date_range_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) ~ (\d{1,2}월 \d{1,2}일) 휴가입니다.")
    
    # 반차 패턴
    half_day_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) (오후|오전)?")

    # 하루종일
    all_day_match = all_day_pattern.match(message)
    if all_day_match:
        return {
            "name": all_day_match.group(1),
            "date": convert_to_iso_date(all_day_match.group(2)),
            "type": "연차"
        }

    # 날짜 범위
    range_match = date_range_pattern.match(message)
    if range_match:
        name = range_match.group(1)
        start_date = convert_to_iso_date(range_match.group(2))
        end_date = convert_to_iso_date(range_match.group(3))
        return {
            "name": name,
            "date_range": (start_date, end_date),
            "type": "연차"
        }

    # 반차
    half_day_match = half_day_pattern.match(message)
    if half_day_match:
        name = half_day_match.group(1)
        date = convert_to_iso_date(half_day_match.group(2))
        half_day_type = "오후반차" if half_day_match.group(3) == "오후" else "오전반차"
        return {
            "name": name,
            "date": date,
            "type": half_day_type
        }

    return None

NOTION_URL = "https://api.notion.com/v1/pages"
NOTION_SEARCH_URL = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

def check_duplicate_date(vacation_date):
    """Notion 데이터베이스에서 중복 날짜 확인."""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2021-08-16"
    }
    query = {
        "filter": {
            "property": "날짜",
            "date": {
                "equals": vacation_date
            }
        }
    }
    response = requests.post(NOTION_SEARCH_URL, headers=headers, json=query)

    if response.status_code == 200:
        results = response.json().get("results", [])
        return len(results) > 0
    else:
        print(f"Failed to check duplicates: {response.status_code}, {response.text}")
        return False



def add_to_notion_calendar(vacation_info):
    """Notion 데이터베이스에 휴가 정보를 추가합니다."""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2021-08-16"
    }

    if "date_range" in vacation_info:
        start_date = vacation_info["date_range"][0]
        end_date = vacation_info["date_range"][1]
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        
        # 두 날짜 사이의 모든 날짜 생성
        current_date = start_date_obj
        while current_date <= end_date_obj:
            title = f"[{vacation_info['type']}] {vacation_info['name']}"
            data = {
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Name": {
                        "title": [{"text": {"content": title}}]
                    },
                    "이름": {
                        "rich_text": [{"text": {"content": vacation_info["name"]}}]
                    },
                    "날짜": {
                        "date": {"start": current_date.strftime("%Y-%m-%d")}
                    },
                    "휴가유형": {
                        "select": {"name": vacation_info["type"]}
                    }
                }
            }
            response = requests.post(NOTION_URL, headers=headers, json=data)
            if response.status_code == 200:
                print(f"{current_date.strftime('%Y-%m-%d')}에 추가되었습니다.")
            else:
                print(f"Failed to add to Notion: {response.status_code}, {response.text}")
            current_date += timedelta(days=1)

    else:
        title = f"[{vacation_info['type']}] {vacation_info['name']}"
        data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Name": {
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

def delete_from_notion_calendar(vacation_info):
    """Notion 데이터베이스에서 해당 정보를 삭제합니다."""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2021-08-16"
    }
    query = {
        "filter": {
            "property": "이름",
            "rich_text": {
                "equals": vacation_info["name"]
            }
        }
    }
    response = requests.post(NOTION_SEARCH_URL, headers=headers, json=query)
    
    if response.status_code == 200:
        results = response.json().get("results", [])
        for page in results:
            delete_url = f"https://api.notion.com/v1/pages/{page['id']}"
            delete_response = requests.delete(delete_url, headers=headers)
            if delete_response.status_code == 200:
                print(f"{vacation_info['name']}의 휴가가 삭제되었습니다.")
            else:
                print(f"Failed to delete from Notion: {delete_response.status_code}, {delete_response.text}")
    else:
        print(f"Failed to search for pages to delete: {response.status_code}, {response.text}")

def main():
    """메인 함수: Slack 메시지를 가져와서 Notion에 추가합니다."""
    messages = get_recent_messages()
    for msg in messages:
        text = msg.get("text", "")
        vacation_info = parse_message(text)
        if vacation_info:
            if vacation_info["type"] == "cancel":
                delete_from_notion_calendar({"name": vacation_info["message"].split(" - ")[0]})
            elif "date_range" in vacation_info:
                add_to_notion_calendar(vacation_info)
            else:
                if not check_duplicate_date(vacation_info["date"]):
                    add_to_notion_calendar(vacation_info)
                else:
                    print(f"{vacation_info['name']}의 {vacation_info['date']}에 대한 중복 데이터가 있습니다.")

if __name__ == "__main__":
    main()
