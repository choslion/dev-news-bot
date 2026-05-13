"""
개발 뉴스 봇 — 매일 하나의 주제를 골라 심층 분석 글을 Notion에 게시
카테고리를 날짜 기준으로 순환하며, 해당 날의 피드에서 가장 흥미로운 주제를 선택
"""

import os
import re
import feedparser
from datetime import datetime, timezone
from anthropic import Anthropic
from notion_client import Client

anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
notion    = Client(auth=os.environ["NOTION_API_KEY"])

NOTION_PARENT_PAGE_ID = os.environ["NOTION_NEWS_PAGE_ID"]

CATEGORIES = [
    {
        "name": "🟢 Nuxt / Vue",
        "feeds": [
            "https://nuxt.com/blog.xml",
            "https://blog.vuejs.org/feed.rss",
        ],
    },
    {
        "name": "🚀 배포 · DevOps",
        "feeds": [
            "https://github.blog/engineering.atom",
            "https://www.docker.com/blog/feed/",
        ],
    },
    {
        "name": "🎨 프론트엔드",
        "feeds": [
            "https://css-tricks.com/feed/",
            "https://web.dev/feed.xml",
        ],
    },
    {
        "name": "🤖 AI · 개발 트렌드",
        "feeds": [
            "https://hnrss.org/frontpage?points=100",
            "https://dev.to/feed/tag/ai",
        ],
    },
]

MAX_ITEMS_PER_FEED = 5


def get_todays_category() -> dict:
    day_index = datetime.now(timezone.utc).timetuple().tm_yday % len(CATEGORIES)
    return CATEGORIES[day_index]


def fetch_articles(category: dict) -> list[dict]:
    articles = []
    for url in category["feeds"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                articles.append({
                    "title":   entry.get("title", "제목 없음"),
                    "link":    entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[:800],
                })
        except Exception as e:
            print(f"[경고] {url} 피드 오류: {e}")
    return articles


def write_deep_dive(articles: list[dict], category_name: str) -> str:
    articles_text = "\n".join(
        f"- 제목: {a['title']}\n  링크: {a['link']}\n  내용: {a['summary']}\n"
        for a in articles
    )

    prompt = f"""아래는 오늘 '{category_name}' 분야에서 수집한 기사 목록이야.

이 중에서 개발자에게 가장 흥미롭고 실무와 연결되는 주제 하나를 골라서, 아래 구성으로 한국어 글을 작성해줘.

[구성]
1. 오늘의 주제 한 줄 소개 (제목 느낌으로)
2. 개념 설명 — 이게 뭔지, 어떤 맥락에서 나온 건지
3. 왜 지금 주목받는가 — 업계 흐름이나 최근 변화와 연결
4. 실무에 어떻게 적용할 수 있나 — 구체적으로
5. 한 줄 의견 — 개인적인 시각이나 전망

[말투]
- "~입니다", "~이다", "~한다" 혼용. 읽기 자연스러울 정도로만 정중하게.
- 딱딱하지 않게, 개발 블로그 글 느낌
- 원문 링크 반드시 포함

[주의]
- AI가 쓴 티 나지 않게
- "요약", "자동화", "AI가 작성" 같은 표현 금지
- 각 섹션에 마크다운 제목(##) 사용

기사 목록:
{articles_text}"""

    response = anthropic.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def extract_title(content: str) -> str:
    """글 첫 줄 또는 첫 ## 제목을 페이지 제목으로 추출"""
    for line in content.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:60]
    return "오늘의 개발 이야기"


def post_to_notion(content: str, category_name: str):
    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    weekdays  = ["월", "화", "수", "목", "금", "토", "일"]
    weekday   = weekdays[datetime.now().weekday()]

    topic_title = extract_title(content)
    page_title  = f"{today_str} ({weekday}) — {topic_title}"

    # 카테고리 태그 블록
    header_block = {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "📌"},
            "rich_text": [{"type": "text", "text": {"content": category_name}}],
            "color": "gray_background",
        },
    }

    divider = {"object": "block", "type": "divider", "divider": {}}

    def parse_rich_text(text: str) -> list:
        """**bold** 및 링크를 rich_text 배열로 변환"""
        rich = []
        # **bold** 와 URL을 함께 처리
        pattern = re.compile(r'\*\*(.+?)\*\*|https?://\S+')
        last = 0
        for m in pattern.finditer(text):
            if m.start() > last:
                rich.append({"type": "text", "text": {"content": text[last:m.start()]}})
            if m.group(0).startswith("**"):
                rich.append({"type": "text", "text": {"content": m.group(1)}, "annotations": {"bold": True}})
            else:
                url = m.group(0).rstrip(".,)")
                rich.append({"type": "text", "text": {"content": url, "link": {"url": url}}})
            last = m.end()
        if last < len(text):
            rich.append({"type": "text", "text": {"content": text[last:]}})
        return rich or [{"type": "text", "text": {"content": text}}]

    # 본문을 줄 단위로 Notion 블록 변환
    body_blocks = []
    first_heading = True
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            body_blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]},
            })
            first_heading = False
        elif stripped.startswith("## "):
            text = stripped[3:]
            # 첫 번째 ## 는 heading_1, 이후는 구분선 + heading_2
            if first_heading:
                body_blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {"rich_text": [{"type": "text", "text": {"content": text}}]},
                })
                first_heading = False
            else:
                body_blocks.append(divider)
                body_blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
                })
        elif stripped.startswith("### "):
            body_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]},
            })
        elif stripped.startswith("- ") or stripped.startswith("* "):
            body_blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_rich_text(stripped[2:])},
            })
        elif stripped.startswith("> "):
            # 인용 블록
            body_blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": parse_rich_text(stripped[2:])},
            })
        else:
            # 의견 섹션 키워드 감지 → 콜아웃
            opinion_keywords = ("한 줄 의견", "개인 의견", "전망", "마치며", "생각해보면")
            if any(kw in stripped for kw in opinion_keywords):
                body_blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "💬"},
                        "rich_text": parse_rich_text(stripped),
                        "color": "blue_background",
                    },
                })
            else:
                body_blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": parse_rich_text(stripped)},
                })

    children = [header_block, divider, *body_blocks]

    notion.pages.create(
        parent={"page_id": NOTION_PARENT_PAGE_ID},
        properties={
            "title": {"title": [{"text": {"content": page_title}}]}
        },
        icon={"type": "emoji", "emoji": "📰"},
        children=children[:100],
    )
    print(f"✅ Notion 포스팅 완료: {page_title}")


def main():
    print("🚀 뉴스 봇 시작...")

    category = get_todays_category()
    print(f"📂 오늘의 카테고리: {category['name']}")

    print("📡 RSS 피드 수집 중...")
    articles = fetch_articles(category)
    print(f"✅ {len(articles)}개 기사 수집 완료")

    print("✍️ 심층 글 작성 중...")
    content = write_deep_dive(articles, category["name"])

    print("📝 Notion 포스팅 중...")
    post_to_notion(content, category["name"])

    print("🎉 완료!")


if __name__ == "__main__":
    main()
