import os
import json
import requests
from datetime import datetime

X_BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

HEADERS = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
KOREA_WOEID = 23424868
PREV_FILE = "previous_trends.json"

def get_korea_trends(max_trends=15):
    url = f"https://api.x.com/2/trends/by/woeid/{KOREA_WOEID}"
    params = {
        "max_trends": max_trends,
        "trend.fields": "trend_name,tweet_count"
    }
    res = requests.get(url, headers=HEADERS, params=params, timeout=30)
    res.raise_for_status()
    return res.json().get("data", [])

def get_related_posts(trend_name, max_results=10):
    query = f'"{trend_name}" lang:ko -is:retweet'
    url = "https://api.x.com/2/tweets/search/recent"
    params = {
        "query": query,
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics,text"
    }
    res = requests.get(url, headers=HEADERS, params=params, timeout=30)
    if res.status_code != 200:
        return []
    return res.json().get("data", [])

def engagement_score(post):
    m = post.get("public_metrics", {})
    return (
        m.get("like_count", 0)
        + m.get("retweet_count", 0) * 2
        + m.get("reply_count", 0) * 1.5
        + m.get("quote_count", 0) * 2
    )

def load_previous():
    if not os.path.exists(PREV_FILE):
        return set()
    with open(PREV_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data)

def save_current(names):
    with open(PREV_FILE, "w", encoding="utf-8") as f:
        json.dump(list(names), f, ensure_ascii=False, indent=2)

def enrich(trends, limit=6):
    results = []
    for t in trends[:limit]:
        name = t.get("trend_name", "")
        posts = get_related_posts(name, max_results=10)
        results.append({"trend": t, "posts": posts})
    return results

def section_header(title):
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{title}*"}
    }

def trend_blocks(items):
    blocks = []
    for i, item in enumerate(items, 1):
        trend = item["trend"]
        posts = item["posts"]
        name = trend.get("trend_name", "")
        count = trend.get("tweet_count")
        count_str = f" · {count:,}건" if count else ""

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{i}. {name}*{count_str}"}
        })

        if posts:
            top = sorted(posts, key=engagement_score, reverse=True)[0]
            text = top.get("text", "").replace("\n", " ")
            if len(text) > 65:
                text = text[:65] + "..."
            link = f"https://x.com/i/status/{top['id']}"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{text}\n<{link}|원글 보기>"}
            })
        else:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_관련 게시물 없음_"}
            })
        blocks.append({"type": "divider"})
    return blocks

def build_blocks(ongoing, new):
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 한국 트렌드 리포트"}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": today}]
        },
        {"type": "divider"},
    ]

    # 유지 중인 트렌드
    blocks.append(section_header("🔁 유지 중인 트렌드"))
    if ongoing:
        blocks.extend(trend_blocks(ongoing))
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_없음 (오늘 처음 실행이거나 겹치는 트렌드 없음)_"}
        })
        blocks.append({"type": "divider"})

    # 신규 트렌드
    blocks.append(section_header("🆕 신규 트렌드"))
    if new:
        blocks.extend(trend_blocks(new))
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_없음_"}
        })

    # 마지막 divider 제거
    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    return blocks

def send_to_slack(blocks):
    payload = {
        "blocks": blocks,
        "text": "한국 트렌드 리포트"
    }
    res = requests.post(SLACK_WEBHOOK, json=payload, timeout=30)
    res.raise_for_status()

def main():
    previous = load_previous()
    current_trends = get_korea_trends()

    current_names = []
    for t in current_trends:
        name = t.get("trend_name")
        if name:
            current_names.append(name)

    ongoing_trends = [t for t in current_trends if t.get("trend_name") in previous]
    new_trends = [t for t in current_trends if t.get("trend_name") not in previous]

    ongoing_data = enrich(ongoing_trends, limit=5)
    new_data = enrich(new_trends, limit=5)

    blocks = build_blocks(ongoing_data, new_data)
    send_to_slack(blocks)

    # 오늘 목록 저장 (내일 비교용)
    save_current(current_names)
    print("Slack 전송 완료 + previous_trends.json 업데이트")

if __name__ == "__main__":
    main()
