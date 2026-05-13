"""
📰 개발 뉴스 자동 수집 → Claude 요약 → Notion 포스팅 봇
매일 오전 9시 GitHub Actions로 자동 실행
"""

import os
import feedparser
from datetime import datetime, timezone
from anthropic import Anthropic
from notion_client import Client

# ── 클라이언트 초기화 ─────────────────────────────────────
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
notion    = Client(auth=os.environ["NOTION_API_KEY"])

NOTION_PARENT_PAGE_ID = os.environ["NOTION_NEWS_PAGE_ID"]

# ── RSS 피드 정의 ──────────────────────────────────────────
RSS_FEEDS = {
    "🟢 Nuxt / Vue": [
        "https://nuxt.com/blog.xml",
        "https://blog.vuejs.org/feed.rss",
    ],
    "🚀 배포 · DevOps": [
        "https://github.blog/engineering.atom",
        "https://www.docker.com/blog/feed/",
    ],
    "🎨 프론트엔드": [
        "https://css-tricks.com/feed/",
        "https://web.dev/feed.xml",
    ],
    "🤖 AI · 개발 트렌드": [
        "https://hnrss.org/frontpage?points=100",  # Hacker News 인기글
        "https://dev.to/feed/tag/ai",
    ],
}

MAX_ITEMS_PER_FEED = 3  # 피드당 최대 기사 수


def fetch_articles(feeds: dict) -> dict:
    """RSS 피드에서 오늘 기사 수집"""
    result = {}
    today = datetime.now(timezone.utc).date()

    for category, urls in feeds.items():
        articles = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                    articles.append({
                        "title": entry.get("title", "제목 없음"),
                        "link":  entry.get("link", ""),
                        "summary": entry.get("summary", entry.get("description", ""))[:500],
                    })
            except Exception as e:
                print(f"[경고] {url} 피드 오류: {e}")

        result[category] = articles[:MAX_ITEMS_PER_FEED * 2]  # 카테고리당 최대 6개

    return result


def summarize_with_claude(articles: dict) -> str:
    """Claude로 기사 한국어 요약"""
    articles_text = ""
    for category, items in articles.items():
        articles_text += f"\n## {category}\n"
        for item in items:
            articles_text += f"- 제목: {item['title']}\n  링크: {item['link']}\n  내용: {item['summary']}\n\n"

    prompt = f"""아래 기사들을 읽고, 개발자 독자에게 오늘 눈에 띈 뉴스를 한국어로 정리해줘.

규칙:
- AI가 생성한 티 나면 안 됨. 개발 좀 하는 사람이 직접 읽고 골라서 쓴 것처럼 자연스럽게
- 각 카테고리마다 2~3개 선택
- 각 뉴스는 2~3문장. "이게 왜 흥미롭냐면..." 식의 개인 의견 한 줄 포함
- 말투는 "~다", "~네", "~함" 같은 블로그/노트 스타일 (존댓말 X)
- AI, 요약, 자동화 같은 단어 쓰지 말 것
- 원문 링크는 반드시 포함

기사 목록:
{articles_text}

출력 형식 (반드시 이 구조로):
[오늘의 요약]
오늘 전체 뉴스를 2~3문장으로 압축. 독자가 제목만 보고도 오늘 뭐가 있었는지 알 수 있게.
[/오늘의 요약]

각 카테고리 제목 아래 뉴스 내용과 링크를 작성."""

    response = anthropic.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def _parse_today_summary(text: str) -> tuple[str, str]:
    """[오늘의 요약]...[/오늘의 요약] 태그를 파싱해 (요약, 본문) 반환"""
    import re
    match = re.search(r"\[오늘의 요약\](.*?)\[/오늘의 요약\]", text, re.DOTALL)
    if match:
        daily_summary = match.group(1).strip()
        body = text[:match.start()] + text[match.end():]
    else:
        daily_summary = ""
        body = text
    return daily_summary, body.strip()


def post_to_notion(summary: str, articles: dict):
    """Notion에 오늘의 뉴스 페이지 생성"""
    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    weekdays  = ["월", "화", "수", "목", "금", "토", "일"]
    weekday   = weekdays[datetime.now().weekday()]

    daily_summary, body = _parse_today_summary(summary)

    # 페이지 제목
    title = f"📰 {today_str} ({weekday}) 개발 뉴스"

    # Notion 블록 구성
    summary_blocks = []
    if daily_summary:
        summary_blocks = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "📌"},
                    "rich_text": [{"type": "text", "text": {"content": "오늘의 요약"}}],
                    "color": "gray_background"
                }
            },
            *[
                {"object": "block", "type": "quote", "quote": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }}
                for line in daily_summary.split("\n") if line.strip()
            ],
        ]

    children = [
        *summary_blocks,
        # 구분선
        {"object": "block", "type": "divider", "divider": {}},
        # 요약 본문 (단락으로 분리)
        *[
            {"object": "block", "type": "paragraph", "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": line}}]
            }}
            for line in body.split("\n") if line.strip()
        ],
        # 구분선
        {"object": "block", "type": "divider", "divider": {}},
        # 원문 링크 섹션
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "🔗 원문 링크 모음"}}]
            }
        },
        *[
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"[{cat}] "}},
                        {"type": "text", "text": {
                            "content": item["title"],
                            "link": {"url": item["link"]}
                        }}
                    ]
                }
            }
            for cat, items in articles.items()
            for item in items
            if item.get("link")
        ],
    ]

    # Notion 페이지 생성
    notion.pages.create(
        parent={"page_id": NOTION_PARENT_PAGE_ID},
        properties={
            "title": {"title": [{"text": {"content": title}}]}
        },
        icon={"type": "emoji", "emoji": "📰"},
        children=children[:100],  # Notion API 블록 제한
    )
    print(f"✅ Notion 포스팅 완료: {title}")


def main():
    print("🚀 뉴스 봇 시작...")

    print("📡 RSS 피드 수집 중...")
    articles = fetch_articles(RSS_FEEDS)

    total = sum(len(v) for v in articles.values())
    print(f"✅ 총 {total}개 기사 수집 완료")

    print("🤖 Claude 요약 중...")
    summary = summarize_with_claude(articles)

    print("📝 Notion 포스팅 중...")
    post_to_notion(summary, articles)

    print("🎉 완료!")


if __name__ == "__main__":
    main()
