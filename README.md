# 📰 개발 뉴스 자동화 봇

Nuxt/Vue, DevOps, 프론트엔드, AI 트렌드 뉴스를 10일마다 자동 수집 →  
Claude가 한국어로 요약 → Notion에 자동 포스팅

---

## 📁 파일 구조

```
├── .github/
│   └── workflows/
│       └── daily_news.yml   # GitHub Actions 스케줄러
├── main.py                  # 뉴스 수집 + 요약 + 포스팅
├── requirements.txt
└── README.md
```

---

## ⚙️ 세팅 방법

### 1. GitHub Secrets 등록

GitHub 레포 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic 콘솔에서 발급 |
| `NOTION_API_KEY` | Notion Integrations에서 발급 |
| `NOTION_NEWS_PAGE_ID` | `35ff0804-3343-8162-8ab7-df545ef2be5d` |

### 2. Notion Integration 연결

1. https://www.notion.so/my-integrations 접속
2. 새 Integration 생성 → API 키 복사
3. 삽질일기 페이지 → 우측 상단 `...` → **연결 추가** → 만든 Integration 선택

### 3. 레포에 파일 푸시

```bash
git add .
git commit -m "feat: 개발 뉴스 자동화 봇 추가"
git push
```

### 4. 수동 테스트 실행

GitHub → Actions 탭 → Daily Dev News Bot → Run workflow

---

## 🕐 실행 시간

10일마다 오전 9시 (KST) 자동 실행
