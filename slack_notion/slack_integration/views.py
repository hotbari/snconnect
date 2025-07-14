import os
import re
import requests
import ssl
import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta

load_dotenv()

# 환경 변수 로드
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# SSL 컨텍스트 설정
ssl_context = ssl.create_default_context(cafile=certifi.where())
slack_client = WebClient(token=SLACK_TOKEN, ssl=ssl_context)


def convert_to_iso_date(date_str):
    """월/일 형식의 날짜 문자열을 ISO 8601 형식으로 변환"""
    try:
        current_year = datetime.now().year
        date_with_year_str = f"{current_year}년 {date_str}"
        date_obj = datetime.strptime(date_with_year_str, "%Y년 %m월 %d일")
        return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        print(f"잘못된 날짜 형식입니다: {date_str}")
        return None


def parse_message(message):
    """메시지에서 휴가 신청 정보 추출"""
    if "취소되었습니다" in message:
        return {"type": "cancel", "message": message}

    all_day_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) 하루종일 휴가입니다.")
    date_range_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) ~ (\d{1,2}월 \d{1,2}일) 휴가입니다.")
    half_day_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) (오후|오전)")

    all_day_match = all_day_pattern.match(message)
    if all_day_match:
        return {
            "name": all_day_match.group(1),
            "date": convert_to_iso_date(all_day_match.group(2)),
            "type": "연차"
        }

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


@csrf_exempt
def slack_events(request):
    """Slack 이벤트를 처리합니다."""
    if request.method == "POST":
        event_data = request.json()
        if "event" in event_data:
            event = event_data["event"]
            if event.get("type") == "message" and "text" in event:
                text = event["text"]
                vacation_info = parse_message(text)
                if vacation_info:
                    if vacation_info["type"] == "cancel":
                        delete_from_notion_calendar({"name": vacation_info["message"].split(" - ")[0]})
                    else:
                        add_to_notion_calendar(vacation_info)
        return JsonResponse({"status": "ok"})
