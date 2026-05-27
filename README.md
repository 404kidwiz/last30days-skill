# last30days

> Research what people **actually** say about any topic in the last 30 days.

![last30days poster](./assets/poster.png)

A Claude Code skill that pulls real posts, discussions, reactions, and engagement signals from Reddit, X/Twitter, YouTube, TikTok, Hacker News, Polymarket, GitHub, Bluesky, and the web — then groups everything by **story and theme**, not by source.

Built by [@mvanhorn](https://github.com/mvanhorn) · v3.2.1 · MIT · Deployed and extended by [DaWizKid](https://github.com/404kidwiz)

---

## Why this exists

Most AI research tools either hit one source (just Reddit, just web) or return a flat dump of links sorted by recency. `last30days` does three things differently:

1. **Multi-source in one pass** — Reddit, X, YouTube, TikTok, HN, Polymarket, GitHub, Bluesky, and web search all run in parallel
2. **Cluster-first output** — results grouped by narrative thread (story/theme), not by platform
3. **Engagement-weighted** — score = reach × recency × relevance, so a 10k-upvote thread from 3 days ago beats a 50-upvote thread from yesterday

---

## Quick start

```
/last30days nvidia earnings reaction
/last30days AI video tools
/last30days what users want in React 19
/last30days Sam Altman vs Elon Musk AI safety debate
```

The skill auto-detects what kind of query you're making (general topic, named person, product, comparison) and adjusts its research plan accordingly.

---

## Sources covered

| Platform | What it pulls | Auth required |
|----------|--------------|---------------|
| **Reddit** | Posts, comments, engagement, subreddit expansion | No (public API) |
| **X / Twitter** | Posts, threads, engagement — by handle, keyword, or hashtag | Optional (AUTH_TOKEN + CT0 for higher rate limits) |
| **YouTube** | Videos, comments, engagement metrics | No |
| **TikTok** | Videos by hashtag and creator | ScrapeCreators API (optional) |
| **Hacker News** | Stories, comments, Ask HN threads | No |
| **Polymarket** | Prediction markets — bets as a sentiment signal | No |
| **GitHub** | Repo activity, issues, discussions (repo and user mode) | No |
| **Bluesky** | Posts by handle and keyword | Optional (BSKY_HANDLE + BSKY_APP_PASSWORD) |
| **Mastodon** | Instance-scoped search | Optional (MASTODON_INSTANCE) |
| **Lemmy** | Instance-scoped communities | Optional (LEMMY_INSTANCE) |
| **PeerTube** | Video search | Optional (PEERTUBE_INSTANCE) |
| **StackExchange** | Questions, answers, tags | Optional (STACKEXCHANGE_API_KEY) |
| **Digg** | Story aggregation | No |
| **TruthSocial** | Posts | Optional (TRUTHSOCIAL_TOKEN) |
| **Instagram** | Creator posts | ScrapeCreators API (optional) |
| **Pinterest** | Boards and pins | No |
| **Google News** | News articles | No |
| **GDELT** | Global news events database | No |
| **DuckDuckGo** | Web search | No |
| **Arxiv** | Academic papers | No |
| **Dev.to** | Developer blog posts | No |
| **RSS feeds** | Any configured RSS source | No |
| **Exa** | Neural web search with semantic reranking | OPENAI/EXA API key (optional) |
| **Apify** | Scraping-backed deep platform access | APIFY_API_TOKEN (optional) |
| **BrowserOS** | Browser-based scraping for paywalled or JS-heavy pages | BrowserOS MCP (optional) |
| **ScrapeCreators** | TikTok and Instagram creator content | SCRAPECREATORS_API_KEY (optional) |

---

## Output format

Results are returned in **v3 cluster-first format**: each cluster is one narrative thread found across multiple platforms, not a flat source-by-source dump.

```
🌐 last30days v3.2.1 · synced 2026-05-26

What I learned:

**The dominant narrative this week...** [cluster 1 prose paragraph]

**A counter-signal is emerging...** [cluster 2 prose paragraph]

**Polymarket is pricing this at 73%...** [prediction market signal if applicable]

KEY PATTERNS from the research:
1. [Pattern with inline link to source]
2. [Pattern with inline link to source]
...

---
✅ All agents reported back!
🟠 Reddit: r/MachineLearning, r/LocalLLaMA, r/artificial (+ 3 peers)
🔵 X: @sama, @elonmusk, @karpathy
🔴 YouTube: 12 videos, 847k views
🩷 TikTok: #AItools 2.4M views
🟡 HN: 3 threads, 1.2k points
🟢 GitHub: pytorch/pytorch, 47 recent issues
---
```

---

## Engine flags

### Named entity resolution (person topics)

When researching a person, use all applicable flags:

```bash
/last30days Sam Altman
# Engine resolves: --x-handle=sama --github-user=sama --subreddits=singularity,MachineLearning,OpenAI --x-related=OpenAI,AnthropicAI
```

Available flags the engine uses internally:

| Flag | Purpose |
|------|---------|
| `--x-handle={handle}` | X/Twitter primary handle for the topic |
| `--x-related={h1,h2,...}` | Related handles (collaborators, company, commentators) |
| `--github-user={user}` | GitHub user profile mode |
| `--github-repo={owner/repo}` | GitHub repo activity mode |
| `--subreddits={sub1,sub2,...}` | Targeted subreddit list |
| `--tiktok-hashtags={h1,...}` | TikTok hashtag targeting |
| `--tiktok-creators={c1,...}` | TikTok creator targeting |
| `--ig-creators={c1,...}` | Instagram creator targeting |
| `--auto-resolve` | Belt-and-suspenders: let engine self-resolve when handles are uncertain |
| `--competitors={a,b,c}` | Comparison mode — runs parallel research on each entity |
| `--plan='{...}'` | Pass a JSON query plan (used by the AI planner) |

### Comparison mode

```
/last30days Claude vs GPT-5 vs Gemini
/last30days Cursor vs Windsurf vs Copilot
```

Comparison queries trigger a side-by-side output with a `## Quick Verdict` section and a `## Head-to-Head` breakdown per entity.

---

## Configuration

All credentials live in `~/.config/last30days/.env`. Run the setup wizard on first use:

```bash
python3 ~/.claude/skills/last30days/scripts/last30days.py --setup
```

### Full environment variable reference

```bash
# Core scraping (boosts TikTok, Instagram coverage)
SCRAPECREATORS_API_KEY=your_key

# Apify (deep scraping for paywalled platforms)
APIFY_API_TOKEN=your_token

# X / Twitter (higher rate limits, private timeline access)
AUTH_TOKEN=your_x_auth_token
CT0=your_x_ct0_cookie

# Bluesky
BSKY_HANDLE=yourhandle.bsky.social
BSKY_APP_PASSWORD=your_app_password

# LLM providers (for internal query planning — any one is enough)
OPENAI_API_KEY=sk-...
XAI_API_KEY=xai-...
OPENROUTER_API_KEY=or-...
PARALLEL_API_KEY=par-...

# Web search
BRAVE_API_KEY=your_brave_key

# Decentralized platforms
MASTODON_INSTANCE=mastodon.social
LEMMY_INSTANCE=lemmy.world
PEERTUBE_INSTANCE=peertube.social

# Academic / developer
STACKEXCHANGE_API_KEY=your_key

# Scrapling stealth mode (advanced browser fingerprinting)
SCRAPLING_STEALTH=1

# TruthSocial
TRUTHSOCIAL_TOKEN=your_token
```

No credentials are required for a basic run. The skill degrades gracefully — unconfigured sources are silently skipped.

---

## Automated briefings (watchlist + cron)

Track topics automatically with the watchlist and briefing system:

```bash
# Add topics to your watchlist
python3 ~/.claude/skills/last30days/scripts/watchlist.py add "AI funding rounds"
python3 ~/.claude/skills/last30days/scripts/watchlist.py add "Rust vs Go performance"
python3 ~/.claude/skills/last30days/scripts/watchlist.py list

# Generate a briefing across all watchlist topics
python3 ~/.claude/skills/last30days/scripts/briefing.py

# Set up a daily cron (macOS/Linux)
# 08:00 every morning → briefing saved to ~/Documents/Last30Days/
0 8 * * * python3 ~/.claude/skills/last30days/scripts/briefing.py >> ~/last30days-cron.log 2>&1
```

Briefings are saved as Markdown to `LAST30DAYS_MEMORY_DIR` (default: `~/Documents/Last30Days/`).

---

## How the engine works

```
User query
    │
    ▼
Step 0.45 — Query quality pre-flight
    │  (catches keyword traps, reframes ambiguous topics)
    ▼
Step 0.5 — Handle resolution (person/brand/product topics)
    │  (resolves X handles, GitHub users, subreddits)
    ▼
Step 0.55 — Platform expansion
    │  (infers TikTok hashtags, related handles, category-peer subs)
    ▼
JSON query plan generated (--plan flag)
    │
    ▼
Parallel source fetch (Reddit, X, YouTube, TikTok, HN, GitHub, web...)
    │
    ▼
Deduplication → Relevance scoring → Reranking
    │
    ▼
Cluster grouping (by story/theme, engagement-weighted)
    │
    ▼
v3 synthesis: What I learned + KEY PATTERNS + engine footer
```

### Scoring model

Each item scored as: `engagement × recency_decay × source_authority × relevance_to_query`

- Reddit: upvotes + comment count
- X: likes + retweets + replies
- YouTube: views + likes + comment count
- HN: points + comments
- GitHub: stars + recent issues + commits

---

## Architecture

```
last30days/
├── SKILL.md                     # Claude Code skill contract (1707 lines)
├── scripts/
│   ├── last30days.py            # Engine entry point
│   ├── briefing.py              # Watchlist briefing generator
│   ├── watchlist.py             # Watchlist CRUD
│   ├── store.py                 # Research memory / persistence
│   └── lib/
│       ├── pipeline.py          # Orchestration and fanout
│       ├── planner.py           # JSON query plan generator
│       ├── cluster.py           # Narrative clustering
│       ├── rerank.py            # Engagement-weighted reranking
│       ├── relevance.py         # Relevance scoring
│       ├── dedupe.py            # Cross-source deduplication
│       ├── fusion.py            # Multi-source result merging
│       ├── providers.py         # LLM provider abstraction
│       ├── env.py               # Config and credential management
│       ├── reddit.py            # Reddit source adapter
│       ├── bird_x.py            # X/Twitter adapter (BrowserOS)
│       ├── xurl_x.py            # X URL resolver
│       ├── xquik.py             # X quick fetch
│       ├── xai_x.py             # xAI/Grok X integration
│       ├── youtube_yt.py        # YouTube adapter
│       ├── tiktok.py            # TikTok adapter
│       ├── hackernews.py        # HN adapter
│       ├── github.py            # GitHub adapter
│       ├── bluesky.py           # Bluesky adapter
│       ├── mastodon.py          # Mastodon adapter
│       ├── polymarket.py        # Polymarket adapter
│       ├── google_news.py       # Google News adapter
│       ├── gdelt.py             # GDELT global news adapter
│       ├── exa_mcp.py           # Exa neural search adapter
│       ├── apify.py             # Apify scraping adapter
│       ├── browseros_scraper.py # BrowserOS adapter
│       ├── perplexity.py        # Perplexity adapter
│       ├── arxiv.py             # Arxiv paper adapter
│       ├── devto.py             # Dev.to adapter
│       ├── instagram.py         # Instagram adapter
│       ├── pinterest.py         # Pinterest adapter
│       ├── reddit_enrich.py     # Reddit category-peer expansion
│       ├── competitors.py       # Comparison mode engine
│       ├── categories.py        # Topic category taxonomy
│       ├── grounding.py         # Factual grounding layer
│       ├── entity_extract.py    # Named entity extraction
│       ├── signals.py           # Engagement signal processing
│       ├── normalize.py         # Cross-platform normalization
│       ├── render.py            # Output rendering
│       ├── html_render.py       # HTML output rendering
│       ├── ui.py                # Terminal UI
│       ├── setup_wizard.py      # First-run setup wizard
│       ├── preflight.py         # Query pre-flight checks
│       ├── quality_nudge.py     # Output quality validation
│       ├── query.py             # Query parsing
│       ├── snippet.py           # Snippet extraction
│       ├── dates.py             # Date and recency utilities
│       ├── http.py              # HTTP client
│       ├── log.py               # Logging
│       ├── subproc.py           # Subprocess utilities
│       ├── schema.py            # JSON schema definitions
│       └── vendor/
│           └── bird-search/     # Bundled X search library (MIT)
```

---

## Requirements

- Python 3.12+
- Node.js (for X/Twitter bird-search library)
- Claude Code with MCP tools enabled

```bash
# Check your Python version
python3 --version  # needs 3.12+

# Install node if needed (macOS)
brew install node
```

---

## Output voice contract

The v3 output follows a strict format. Key rules the engine enforces:

- **Badge mandatory** on line 1: `🌐 last30days v3.2.1 · synced YYYY-MM-DD`
- **No `Sources:` block at the end** — inline `[text](url)` links only
- **No section headers** (`##`) in body — bold lead-in paragraphs only
- **No em-dashes** — use ` - ` with spaces
- **Engine footer pass-through** verbatim after KEY PATTERNS
- **Cluster-first, not source-first** — don't dump raw Reddit/X threads

---

## Enhancements in this fork

This repository is deployed and extended by [DaWizKid (404kidwiz)](https://github.com/404kidwiz):

| Enhancement | Description |
|-------------|-------------|
| **Apify integration** | Configured with `APIFY_API_TOKEN` for deep scraping of rate-limited platforms |
| **GitHub publishing** | Published to public GitHub with proper `.gitignore` and attribution |
| **Extended tagging** | Added Higgsfield AI integration context for prompt engineering use cases |
| **DaWizKid environment** | Configured alongside `comfy-prompt` and `prompt-master` skills in a unified Claude Code setup |

---

## Credits

**Original author:** [@mvanhorn](https://github.com/mvanhorn)
**Original repository:** [github.com/mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill)
**License:** MIT — see [LICENSE](./LICENSE) if included upstream

**This fork maintained by:** [DaWizKid](https://github.com/404kidwiz) — former music producer turned AI developer, Atlanta metro. Building AI-native workflows and tools on Claude Code + Comfy Cloud + Higgsfield.

---

## Related skills

| Skill | Description |
|-------|-------------|
| [comfy-prompt](https://github.com/404kidwiz/comfy-prompt) | Claude Code skill for Comfy Cloud — 30+ image/video models, MCSLA prompting, cost tracking |
| [prompt-master](https://github.com/404kidwiz) | Optimized prompt generation for any AI tool |

---

*Built for Claude Code. Works with OpenClaw, Hermes Agent, and any agentic runtime that supports skill invocation.*
