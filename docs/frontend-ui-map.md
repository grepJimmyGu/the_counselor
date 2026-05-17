# Frontend UI/UX Map

This document provides a visual route and component map for the `apps/web` frontend.
Use it as a reference when editing page layouts, navigation, or shared UI patterns.

## 1. App structure

- `apps/web/src/app/layout.tsx`
  - App shell, theme + auth providers, global header, skip link
- `apps/web/src/app/globals.css`
  - Global Tailwind/shadcn theme tokens
  - Light/dark palette, financial color tokens, typography
- `apps/web/src/components/nav-header.tsx`
  - Sticky top navigation, responsive mobile drawer, auth menu
- `apps/web/src/components/ui/*`
  - Shared UI primitives: buttons, badges, inputs, cards, tabs, skeletons, tooltips

## 2. Main route tree

```mermaid
flowchart TD
  Home[/] --> Stocks[/stocks]
  Home --> Sentiment[/sentiment]
  Home --> Workspace[/workspace]
  Home --> Community[/community]
  Home --> Templates[/templates]
  Home --> Profile[/profile]
  Home --> Commodities[/commodities/[symbol]]
  Home --> QA[/qa]

  Stocks --> MarketPulse[_market-pulse.tsx]
  Stocks --> StockDetail[/stocks/[ticker]]
  Workspace --> ResearchWorkspace[research-workspace.tsx]
  Templates --> TemplateBrowser[templates/page.tsx]
  Sentiment --> SentimentHub[sentiment/page.tsx]
  Community --> CommunityBoard[community/page.tsx]
  Profile --> Watchlist[profile/page.tsx]
```

## 3. Page entry points

- `/` — `apps/web/src/app/page.tsx`
  - Landing page with hero, pillar cards, snapshot, search, glossary, how-it-works, templates preview
- `/stocks` — `apps/web/src/app/stocks/page.tsx`
  - Renders `apps/web/src/app/stocks/_market-pulse.tsx`
  - Market pulse dashboard with sectors, indexes, CMF, search, and board rows
- `/stocks/[ticker]` — `apps/web/src/app/stocks/[ticker]/page.tsx`
  - Stock detail page with overview, sentiment tab, and research sections
- `/workspace` — `apps/web/src/app/workspace/page.tsx`
  - Research workspace entry point with AI-backed strategy builder
- `/templates` — `apps/web/src/app/templates/page.tsx`
  - Template explorer and run/customize workflow
- `/sentiment` — `apps/web/src/app/sentiment/page.tsx`
  - News & sentiment toolkit hub
- `/community` — `apps/web/src/app/community/page.tsx`
  - Community board and public strategy feed
- `/profile` — `apps/web/src/app/profile/page.tsx`
  - User profile, watchlist, quick links
- `/commodities/[symbol]` — `apps/web/src/app/commodities/[symbol]/page.tsx`
  - Commodity mock evaluation dashboard
- `/qa` — `apps/web/src/app/qa/page.tsx`
  - QA review form for product flow auditing

## 4. Core UI patterns

- Page layout:
  - full-width `main` with `mx-auto`, responsive `px-4 md:px-6 lg:px-8`
  - card groups with `rounded-xl border border-border bg-white shadow-sm`
  - section headers using `font-heading` + `text-sm font-semibold`
- Buttons:
  - primary and outline variants from `components/ui/button.tsx`
  - common classes: `rounded-xl`, `px-6`, `text-sm`, `transition-colors`
- Data cards:
  - subtle hover shadows and border transitions
  - use `bg-white` on content cards and `bg-muted` for muted containers
- Responsive design:
  - `grid gap-5 lg:grid-cols-3` for cards
  - mobile-first stacks with `flex-col md:flex-row`
  - hidden desktop elements using `hidden sm:flex`

## 5. Component hierarchy for UI/UX edits

```mermaid
flowchart TD
  Layout[layout.tsx]
  Layout -->|renders| NavHeader[nav-header.tsx]
  Layout -->|wraps| MainContent[page routes]

  MainContent --> HomePage[app/page.tsx]
  MainContent --> StocksPage[stocks/page.tsx]
  MainContent --> StockDetail[stocks/[ticker]/page.tsx]
  MainContent --> WorkspacePage[workspace/page.tsx]
  MainContent --> TemplatesPage[templates/page.tsx]
  MainContent --> SentimentPage[sentiment/page.tsx]
  MainContent --> CommunityPage[community/page.tsx]
  MainContent --> ProfilePage[profile/page.tsx]
  MainContent --> CommodityPage[commodities/[symbol]/page.tsx]
  MainContent --> QAPage[qa/page.tsx]

  HomePage --> MarketSnapshot[components/home/market-snapshot.tsx]
  HomePage --> AssetSearch[components/home/asset-search.tsx]
  HomePage --> StrategyTeaser[components/home/strategy-teaser.tsx]
  HomePage --> CapabilityGlossary[components/home/capability-glossary.tsx]

  StockDetail --> EvaluationDashboard[stocks/[ticker]/_evaluation-dashboard.tsx]
  StockDetail --> BusinessModelSection[stocks/[ticker]/_business-model-section.tsx]
  StockDetail --> MarketPositionSection[stocks/[ticker]/_market-position-section.tsx]
  StockDetail --> SentimentTab[stocks/[ticker]/_sentiment-tab.tsx]

  CommunityPage --> UpvoteButton[components/community/upvote-button.tsx]
  CommunityPage --> VoteBar[components/community/vote-bar.tsx]
  CommunityPage --> CommentsSection[components/community/comments-section.tsx]

  WorkspacePage --> ResearchWorkspace[components/workspace/research-workspace.tsx]
```

## 6. Editing support tips

- Search `apps/web/src/components/ui` first when changing input, button, badge, card, or tab styles.
- Update global theme values in `apps/web/src/app/globals.css` to shift color palettes consistently.
- Use `text-muted-foreground`, `bg-muted`, and `border-border` for neutral surfaces.
- Apply `shadow-sm` and `hover:border-primary/30` for interactive card depth.
- When modifying page sections, keep the mobile/desktop split in mind: many layouts use `sm:hidden` / `hidden sm:flex`.

## 7. Notes

- The current frontend is a research-first dashboard with strong emphasis on data cards, signal pipelines, and strategy workflows.
- Future UI/UX changes should preserve the shared `button/card/badge` design system and use the route map above to place new pages consistently.
