# 코고가네(KOHgogane) — 디자인 토큰 번들 (styles/tokens 단일소스)

> 오너 결정(2026-06-23): **"v18 토큰만 styles/tokens로 반영. Flask+Jinja+app.css 구조 유지,
> React/컴포넌트 라이브러리로 바꾸지 말 것. app.css :root의 토큰을 단일소스로 쓰고,
> 하드코딩 hex/px 금지. 기존 화면 회귀 없이."**

이 폴더는 proxy-commerce의 디자인 토큰을 **컴포넌트가 아니라 토큰만** 추출한 번들이다.
Claude Design(claude.ai/design)에 올리면, 그 프로젝트가 렌더하는 모든 디자인이
코고가네 팔레트·폰트·간격을 그대로 쓰게 된다.

- `styles.css` — `app.css :root`의 v18 토큰 전체 + 폰트 @import + 토큰을 적용하는 베이스 룩.
- `tokens/tokens.json` — 같은 토큰을 그룹(color/typography/space/radius/shadow/motion/layout/alias)으로 구조화.

이 번들은 `src/static/app.css`의 `:root`에서 **그대로 추출**한 것이라 단일소스를 깨지 않는다.
app.css가 바뀌면 이 번들도 다시 추출해 동기화한다(드리프트 금지).

## 토큰 어휘 (디자인 에이전트용 규칙)

에디토리얼 럭셔리. **화면당 강조색 1개, 이모지 0, 두꺼운 보더 0**(여백 + 얕은 그림자 + 1px 가는 구분선).

| 의미 | 토큰 | 값 | 쓰는 곳 |
|---|---|---|---|
| 주요 행동(CTA) | `var(--orange)` | #F5821F | 화면당 1개. 시작하기/연동하기/등록하기 등 큰 버튼만 |
| 브랜드·링크·현재위치 | `var(--teal)` | #119A8E | 보조 액션, 링크, 활성 내비, 포커스 링 |
| 먹(텍스트/다크) | `var(--ink)` | #1A1714 | 최강 텍스트, 다크 'vault'(랜딩/로그인) 표면 |
| 한지(배경) | `var(--cream)`/`var(--bg)` | #F5EFE3/#F7F2E8 | 기본 배경 |
| 금(악센트) | `var(--gold)` | #C9A24B | 절제된 프리미엄 구분/악센트만(면적 작게) |
| 본문 텍스트 | `var(--text)` / `--text-strong` / `--text-muted` | | 본문/제목/보조 |
| 표면·보더 | `var(--surface)` / `var(--border)` | | 카드/입력 |
| 상태 | `var(--success/--warn/--danger)` | | 성공/경고/위험만 |

- **음영(hover/짙은 단계)**: `--teal-hover`/`--teal-strong`, `--orange-hover`/`--orange-strong`,
  `--gold-ink`/`--gold-ink-strong`. 컴포넌트에서 hover hex를 새로 만들지 말고 이 토큰을 쓴다.
- **악센트 위 텍스트**: `var(--on-accent)`(#FFFFFF).

### 타이포
- 디스플레이/제목 = `var(--font-display)` (Noto Serif KR).
- 본문/UI = `var(--font-ui)` (Pretendard + Inter).
- 크기: `--display-size`(clamp 40~72), `--h1~3-size`, `--body`, `--caption`. 하드코딩 px 금지.

### 간격 — 8px 그리드
모든 패딩/마진/갭은 `var(--space-1..9)`(4·8·12·16·24·32·48·64·96px)의 배수만.

### 라운드/그림자/모션
`--radius-sm/--radius/--radius-lg/--radius-pill`, `--shadow-sm/--shadow/--shadow-lg`,
`--dur-*`/`--ease`(prefers-reduced-motion 존중).

## 올리는 법 (claude.ai/design)

이 토큰 번들은 **준비 완료** 상태다. 실제 업로드는 인증이 필요하다:

- **claude.ai/code(웹) 환경**: `/design-login`이 대화형 터미널을 요구해서 이 세션에선 인증이 안 된다.
  → Claude Design에서 **"Send to Claude Code Web"** 으로 프로젝트를 워크스페이스에 시드하거나,
  로컬 Claude Code에서 `/design-login` 후 이 폴더를 올리면 된다.
- 인증이 되면 DesignSync `finalize_plan`(writes=`styles.css`, `tokens/tokens.json`, `README.md`,
  localDir=이 폴더) → `write_files`로 푸시한다.
