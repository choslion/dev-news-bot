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

이 중에서 개발자에게 가장 흥미롭고 실무와 연결되는 주제 하나를 골라서, 아래 스타일로 한국어 글을 써줘.

---

[레퍼런스 스타일]
토스 테크 블로그 (toss.tech) 글체를 따를 것. 핵심 패턴:

- 도입부: 독자가 실제로 겪어봤을 법한 상황이나 질문으로 시작. "이런 경험 있지 않으셨나요?" 또는 현재 업계에서 다들 고민하는 공통 화두를 꺼내서 공감부터 얻을 것. 추상적 출발 금지.
- 구조: 문제/현상 → 왜 이게 문제인가 → 해결 방향 → 실무 적용 → 독자에게 돌려주는 마무리
- 섹션 제목: 질문형으로. "이게 왜 문제가 됐을까요?", "그래서 어떻게 바꿨냐면요" 같은 식
- 대비 구조 적극 활용: 잘 쓰는 사람 vs 못 쓰는 사람, 이전 방식 vs 새로운 방식 등으로 차이를 직관적으로 보여줄 것
- 단호한 주장 + 균형: "이건 버블입니다. 그러나 안심할 수 없습니다" 식으로, 한쪽만 말하지 말 것
- 독자 배려: 읽다 보면 생길 법한 의문을 한 발 앞서 언급. "이쯤 되면 이런 생각 드실 텐데요" 식으로
- 겸손과 자신감 교차: "제 개인적인 생각이지만", 동시에 "이 방향은 맞다고 봅니다" 같은 직접적 주장

[글 구성]

## (제목 — 호기심을 자극하는 한 줄. 너무 평범하면 안 됨)

(도입부 — 섹션 제목 없이 바로 시작. 2~3문단, 공감 기반)

## (섹션 제목은 질문형으로)
(개념 설명. 처음 접하는 사람도 맥락을 잡을 수 있게. 왜 이게 나왔는지부터)

## (섹션 제목은 질문형으로)
(A vs B 대비 구조나 구체적 사례로 핵심 차이를 보여줄 것. 코드 예시 있으면 코드블록으로)

## (섹션 제목은 질문형으로)
(실무 적용. "활용할 수 있다"가 아니라 실제 상황 시나리오로)

## 마치며
(짧고 솔직하게. 기대되는 점, 아직 아쉬운 점. 독자에게 주체성을 돌려주는 열린 질문으로 끝낼 것)

---

[말투]
- "~요", "~합니다" 체. 딱딱하지 않고 대화하는 느낌
- 문장은 짧게. 한 문장에 두 가지 넣지 말 것
- "살펴보겠습니다", "알아보도록 하겠습니다", "정리하자면", "중요합니다" 절대 금지
- AI가 쓴 티 나면 실패. 엔지니어가 직접 쓴 것처럼

[주의]
- 원문 링크는 자연스럽게 본문에 녹여서 포함
- 코드는 반드시 ```언어 블록으로
- 전체 분량: 800~1200자 내외

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
    page_title  = topic_title

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

    notion_lang_map = {
        "bash": "bash", "sh": "bash", "shell": "bash",
        "python": "python", "py": "python",
        "javascript": "javascript", "js": "javascript",
        "typescript": "typescript", "ts": "typescript",
        "yaml": "yaml", "yml": "yaml",
        "json": "json", "sql": "sql",
        "go": "go", "rust": "rust", "java": "java",
        "css": "css", "html": "html", "xml": "xml",
    }

    # 본문을 줄 단위로 Notion 블록 변환
    body_blocks = []
    first_heading = True
    in_code_block = False
    code_lang = "plain text"
    code_lines: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        # 코드 블록 시작/종료 감지
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                lang_key = stripped[3:].strip().lower()
                code_lang = notion_lang_map.get(lang_key, "plain text")
                code_lines = []
            else:
                in_code_block = False
                body_blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                        "language": code_lang,
                    },
                })
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(line)
            continue

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
