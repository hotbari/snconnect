import os
import re
import requests
import ssl
import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, timedelta


# env 파일에서 환경 변수 로드
load_dotenv()

SLACK_TOKEN = os.getenv("SLACK_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")


# SSL 컨텍스트 설정
ssl_context = ssl.create_default_context(cafile=certifi.where())
slack_client = WebClient(token=SLACK_TOKEN, ssl=ssl_context)

def get_recent_messages():
    """
    Slack에서 최근 메시지 10개 조회 
    """
    try:
        response = slack_client.conversations_history(channel=SLACK_CHANNEL_ID, limit=10)
        return response.get("messages", [])
    
    except SlackApiError as e: # 오류 발생 시 에러 메시지 출력 후 빈 리스트 반환
        print(f"Error fetching messages: {e.response['error']}")
        return []


def convert_to_iso_date(date_str):
    """
    월/일 형식의 날짜 문자열을 ISO 8601 형식으로 변환
    """
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
    print(f"[parse_message 디버그] 원본 메시지: {message}")
    # 취소 메시지: '취소'라는 단어가 포함되어 있으면 삭제 로직 실행
    if "취소" in message:
        try:
            # 이름 추출
            name_part = message.split('-')[0].strip()
            # 날짜 및 유형 추출
            right = message.split('-')[1]
            # 날짜 추출 (예: '7월 18일 오후반차가 취소되었습니다.')
            date_match = re.search(r"(\d{1,2}월 \d{1,2}일)", right)
            date = convert_to_iso_date(date_match.group(1)) if date_match else None
            # 휴가유형 추출
            if "오전" in right:
                vacation_type = "오전반차"
            elif "오후" in right:
                vacation_type = "오후반차"
            elif "하루종일" in right or "연차" in right:
                vacation_type = "연차"
            else:
                vacation_type = "연차"
            print(f"[parse_message 디버그] 취소 파싱: name={name_part}, date={date}, vacation_type={vacation_type}")
            return {
                "type": "cancel",
                "name": name_part,
                "date": date,
                "vacation_type": vacation_type
            }
        except Exception as e:
            print(f"[parse_message 디버그] 취소 파싱 오류: {e}")
            return {"type": "cancel", "name": name_part}
    # 날짜 범위(물결) 포함
    if '~' in message:
        try:
            name_part = message.split('-')[0].strip()
            date_part = message.split('-')[1].split('휴가')[0]
            print(f"[parse_message 디버그] date_part: {date_part}")
            parts = [s.strip() for s in date_part.split('~')]
            if len(parts) != 2:
                print(f"[parse_message 디버그] ~ split 결과가 2개가 아님: {parts}")
                raise ValueError("날짜 범위 파싱 실패")
            start_str, end_str = parts
            for kw in ['하루종일', '오전', '오후']:
                end_str = end_str.replace(kw, '').strip()
            start_date = convert_to_iso_date(start_str)
            end_date = convert_to_iso_date(end_str)
            print(f"[parse_message 디버그] ~ 포함: name={name_part}, start_date={start_date}, end_date={end_date}")
            return {
                "name": name_part,
                "date_range": (start_date, end_date),
                "type": "연차"  # 필요시 '하루종일' 등 키워드로 판별
            }
        except Exception as e:
            print(f"[parse_message 디버그] ~ 파싱 오류: {e}")
    all_day_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) 하루종일 휴가입니다.")
    half_day_pattern = re.compile(r"(.*) - (\d{1,2}월 \d{1,2}일) (오후|오전)?")
    all_day_match = all_day_pattern.match(message)
    print(f"[parse_message 디버그] all_day_pattern 매칭 결과: {all_day_match}")
    if all_day_match:
        return {
            "name": all_day_match.group(1),
            "date": convert_to_iso_date(all_day_match.group(2)),
            "type": "연차"
        }
    half_day_match = half_day_pattern.match(message)
    print(f"[parse_message 디버그] half_day_pattern 매칭 결과: {half_day_match}")
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
    """
    Notion 데이터베이스에서 중복 날짜 확인
    """
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
    """
    Notion 데이터베이스에 휴가 정보를 추가
    """
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2021-08-16"
    }

    if "date_range" in vacation_info:
        start_date = vacation_info["date_range"][0]
        end_date = vacation_info["date_range"][1]
        print(f"[add_to_notion_calendar 디버그] date_range: {vacation_info['date_range']}")
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        print(f"[add_to_notion_calendar 디버그] start_date_obj: {start_date_obj}, end_date_obj: {end_date_obj}")
        # 두 날짜 사이의 모든 날짜 생성
        current_date = start_date_obj
        idx = 1
        while current_date <= end_date_obj:
            print(f"[add_to_notion_calendar 디버그] {idx}번째 반복: current_date={current_date.strftime('%Y-%m-%d')}")
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
            idx += 1
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
    """
    Notion 데이터베이스에서 해당 정보를 삭제합니다.
    (이름+날짜+휴가유형 모두 일치하는 데이터만 삭제)
    """
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2021-08-16",
        "Content-Type": "application/json"
    }
    # AND 조건으로 이름, 날짜, 휴가유형 모두 비교
    filters = [
        {"property": "이름", "rich_text": {"equals": vacation_info["name"]}}
    ]
    if "date" in vacation_info:
        filters.append(
            {"property": "날짜","date": {"equals": vacation_info["date"]}}
            )
        
    if "vacation_type" in vacation_info:
        filters.append(
            {"property": "휴가유형", "select": {"equals": vacation_info["vacation_type"]}}
            )
        
    if "date_range" in vacation_info:
        # 날짜 범위는 start~end 모두 삭제
        start_date, end_date = vacation_info["date_range"]
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        while current <= end:
            filters_with_date = filters.copy()
            filters_with_date.append({"property": "날짜", "date": {"equals": current.strftime("%Y-%m-%d")}})
            query = {"filter": {"and": filters_with_date}}
            response = requests.post(NOTION_SEARCH_URL, headers=headers, json=query)
            if response.status_code == 200:
                results = response.json().get("results", [])
                for page in results:
                    page_id = page['id']
                    patch_url = f"https://api.notion.com/v1/pages/{page_id}"
                    patch_data = {"archived": True}
                    patch_response = requests.patch(patch_url, headers=headers, json=patch_data)
                    if patch_response.status_code == 200:
                        print(f"{vacation_info['name']}의 {current.strftime('%Y-%m-%d')} 휴가가 삭제되었습니다.")
                    else:
                        print(f"Failed to archive in Notion: {patch_response.status_code}, {patch_response.text}")
            else:
                print(f"Failed to search for pages to delete: {response.status_code}, {response.text}")
            current += timedelta(days=1)
        return
    
    # 단일 날짜
    query = {"filter": {"and": filters}}
    response = requests.post(NOTION_SEARCH_URL, headers=headers, json=query)
    if response.status_code == 200:
        results = response.json().get("results", [])
        for page in results:
            page_id = page['id']
            patch_url = f"https://api.notion.com/v1/pages/{page_id}"
            patch_data = {"archived": True}
            patch_response = requests.patch(patch_url, headers=headers, json=patch_data)
            if patch_response.status_code == 200:
                print(f"{vacation_info['name']}의 휴가가 삭제되었습니다.")
            else:
                print(f"Failed to archive in Notion: {patch_response.status_code}, {patch_response.text}")
    else:
        print(f"Failed to search for pages to delete: {response.status_code}, {response.text}")

def main():
    """메인 함수: Slack 메시지를 가져와서 Notion에 추가/삭제합니다."""
    messages = get_recent_messages()
    # 오래된 메시지부터 처리
    for msg in reversed(messages):
        text = msg.get("text", "")
        # 여러 줄이 들어올 경우 한 줄씩 처리
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            vacation_info = parse_message(line)
            if vacation_info:
                if "date_range" in vacation_info:
                    print(f"[디버그] vacation_info: {vacation_info}")
                if vacation_info["type"] == "cancel":
                    delete_from_notion_calendar(vacation_info)
                elif "date_range" in vacation_info:
                    add_to_notion_calendar(vacation_info)
                else:
                    if not check_duplicate_date(vacation_info["date"]):
                        add_to_notion_calendar(vacation_info)
                    else:
                        print(f"{vacation_info['name']}의 {vacation_info['date']}에 대한 중복 데이터가 있습니다.")

if __name__ == "__main__":
    main()
