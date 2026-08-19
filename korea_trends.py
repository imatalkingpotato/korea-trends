import os
import json
import re
import requests
from datetime import datetime
from collections import Counter

X_BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

HEADERS = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
KOREA_WOEID = 23424868
PREV_FILE = "previous_trends.json"

# 1) 트렌드 이름: 아티스트 축하/애정 표현
NAME_EXCLUDE_PATTERNS = [
    r"축하",
    r"사랑해",
    r"생일",
    r"주년",
    r"happy.*day",
    r"그려온",
]

# 2) 게시물 내용: 스팸 / 성인 / 정치 / 주식
SPAM_ADULT_KEYWORDS = [
    "라인", "line", "텔레", "telegram", "출장", "조건만남", "조건 만남",
    "오피", "휴게텔", "마사지", "휴게", "단톡", "카톡", "dm 주세요",
    "선물하기", "카카오선물", "입금", "계좌",
]
POLITICS_KEYWORDS = [
    "민주당", "국힘", "국민의힘", "의회", "의원", "선거", "대선", "총선",
    "대통령", "윤석열", "이재명", "김정은", "북한", "국회",
]
STOCK_KEYWORDS = [
    "코스피", "코스닥", "사이드카", "주가", "매도", "매수", "상한가",
    "하한가", "반도체", "환율", "금리", "선물", "인버스",
]

def get_korea_trends(max_trends=20):
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

def is_celebration_name(name: str) -> bool:
    n = name.lower()
    return any(re.search(p, n, re.IGNORECASE) for p in NAME_EXCLUDE_PATTERNS)

def text_hit_ratio(posts, keywords):
    if not posts:
        return 0.0
    hits = 0
    for p in posts:
        text = (p.get("text") or "").lower()
        if any(k.lower() in text for k in keywords):
            hits += 1
    return hits / len(posts)

def is_template_spam(posts):
    """비슷한 문장이 반복되면 스팸으로 간주"""
    if len(posts) < 4:
        return False
    norms = []
    for p in posts:
        t = re.sub(r"\s+", " ", (p.get("text") or "")).strip()[:40]
        norms.append(t)
    if not norms:
        return False
    most_common_count = Counter(norms).most_common(1)[0][1]
    return most_common_count / len(norms) >= 0.5

def is_bad_trend(name, posts) -> bool:
    # 이름: 축하/애정
    if is_celebration_name(name):
        return True

    # 게시물 기반
    if is_template_spam(posts):
        return True
    if text_hit_ratio(posts, SPAM_ADULT_KEYWORDS) >= 0.3:
        return True
    if text_hit_ratio(posts, POLITICS_KEYWORDS) >= 0.4:
        return True
    if text_hit_ratio(posts, STOCK_KEYWORDS) >= 0.4:
        return True

    # 쓸 만한 글이 없음
    usable = [p for p in posts if engagement_score(p) > 0 and len((p.get("text") or "")) > 10]
    if posts and not usable:
        return True

    return False

def load_previous():
    if not os.path.exists(PREV_FILE):
        return set()
    with open(PREV_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data)

def save_current(names):
    with open(PREV_FILE, "w", encoding="utf-8") as f:
        json.dump(list(names), f, ensure_ascii=False, indent=2)

def enrich(trends, limit=5):
    results = []
    for t in trends[:limit]:
        name = t.get("trend_name", "")
        posts = get_related_posts(name, max_results=10)
        if is_bad_trend(name, posts):
            continue
        # 스팸성 게시물 제거 후 상위 1개만 사용
        clean_posts = []
        for p in posts:
            text = (p.get("text") or "").lower()
            if any(k.lower() in text for k in SPAM_ADULT_KEYWORDS):
                continue
            if any(k.lower() in text for k in POLITICS_KEYWORDS):
                continue
            if any(k.lower() in text for k in STOCK_KEYWORDS):
                continue
            clean_posts.append(p)
        results.append({"trend": t, "posts": clean_posts})
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

    blocks.append(section_header("🔁 유지 중인 트렌드"))
    if ongoing:
        blocks.extend(trend_blocks(ongoing))
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_없음_"}
        })
        blocks.append({"type": "divider"})

    blocks.append(section_header("🆕 신규 트렌드"))
    if new:
        blocks.extend(trend_blocks(new))
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_없음_"}
        })

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

    # 이름만으로 1차 제외 (축하/애정)
    current_trends = [
        t for t in current_trends
        if not is_celebration_name(t.get("trend_name", ""))
    ]

    current_names = [t.get("trend_name") for t in current_trends if t.get("trend_name")]

    ongoing_raw = [t for t in current_trends if t.get("trend_name") in previous]
    new_raw = [t for t in current_trends if t.get("trend_name") not in previous]

    # 게시물 검사 포함 enrich (스팸/성인/정치/주식 트렌드 제거)
    ongoing_data = enrich(ongoing_raw, limit=8)
    new_data = enrich(new_raw, limit=8)

    blocks = build_blocks(ongoing_data[:5], new_data[:5])
    send_to_slack(blocks)

    save_current(current_names)
    print("Slack 전송 완료 + previous_trends.json 업데이트")

if __name__ == "__main__":
    main()
