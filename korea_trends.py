import os
import requests
from datetime import datetime

X_BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

HEADERS = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
KOREA_WOEID = 23424868

def get_korea_trends(max_trends=12):
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

def build_slack_message(trends_data):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"*한국 트렌드 ({today})*\n"]

    for i, item in enumerate(trends_data, 1):
        trend = item["trend"]
        posts = item["posts"]
        count = trend.get("tweet_count")
        count_str = f" ({count:,})" if count else ""

        lines.append(f"*{i}. {trend.get('trend_name')}*{count_str}")

        if not posts:
            lines.append("   · 관련 게시물 없음\n")
            continue

        posts_sorted = sorted(posts, key=engagement_score, reverse=True)[:3]
        for p in posts_sorted:
            text = p.get("text", "").replace("\n", " ")
            if len(text) > 70:
                text = text[:70] + "..."
            score = int(engagement_score(p))
            link = f"https://x.com/i/status/{p['id']}"
            lines.append(f"   · [{score}] {text}")
            lines.append(f"     <{link}|원글 보기>")
        lines.append("")

    return "\n".join(lines)

def send_to_slack(text):
    res = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=30)
    res.raise_for_status()

def main():
    trends = get_korea_trends()
    results = []
    for t in trends[:10]:
        name = t.get("trend_name", "")
        posts = get_related_posts(name, max_results=10)
        results.append({"trend": t, "posts": posts})

    message = build_slack_message(results)
    send_to_slack(message)
    print("Slack 전송 완료")

if __name__ == "__main__":
    main()
