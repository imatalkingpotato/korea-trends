import os
import requests
from datetime import datetime

X_BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

HEADERS = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
KOREA_WOEID = 23424868

def get_korea_trends(max_trends=10):
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

def build_blocks(trends_data):
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 한국 트렌드 리포트"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{today}"
                }
            ]
        },
        {"type": "divider"}
    ]

    for i, item in enumerate(trends_data, 1):
        trend = item["trend"]
        posts = item["posts"]
        name = trend.get("trend_name", "")
        count = trend.get("tweet_count")
        count_str = f" · {count:,}건" if count else ""

        # 트렌드 제목
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{i}. {name}*{count_str}"
            }
        })

        if posts:
            top = sorted(posts, key=engagement_score, reverse=True)[0]
            text = top.get("text", "").replace("\n", " ")
            if len(text) > 70:
                text = text[:70] + "..."
            link = f"https://x.com/i/status/{top['id']}"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{text}\n<{link}|원글 보기>"
                }
            })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_관련 게시물 없음_"
                }
            })

        blocks.append({"type": "divider"})

    # 마지막 divider 제거
    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    return blocks

def send_to_slack(blocks):
    payload = {
        "blocks": blocks,
        "text": "한국 트렌드 리포트"  # 알림용 미리보기 텍스트
    }
    res = requests.post(SLACK_WEBHOOK, json=payload, timeout=30)
    res.raise_for_status()

def main():
    trends = get_korea_trends()
    results = []
    for t in trends[:8]:
        name = t.get("trend_name", "")
        posts = get_related_posts(name, max_results=10)
        results.append({"trend": t, "posts": posts})

    blocks = build_blocks(results)
    send_to_slack(blocks)
    print("Slack 전송 완료")

if __name__ == "__main__":
    main()
