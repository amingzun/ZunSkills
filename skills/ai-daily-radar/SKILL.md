---
name: ai-daily-radar
description: Generate a daily AI news radar from global English-language sources. Use when the user asks for AI daily news, hot AI updates, AI radar, AI intelligence briefings, trending AI projects/papers/models/tools, or scheduled AI information gathering.
---

# AI Daily Radar

## Overview

Generate a concise Markdown briefing of the day's most important AI updates for a technical builder audience. The report focuses on signal, not volume: source title, Chinese title translation, link, heat signal, and a plain Chinese summary with brief explanations for uncommon AI terms.

## Quick Start

Run the bundled script from this skill directory:

```bash
python3 scripts/ai_daily_radar.py --config templates/config.example.json
```

By default it writes Markdown to `outputs/YYYY-MM-DD-ai-daily-radar.md` inside this skill directory and prints a short summary.

Use only the local shell/Python script for execution. Do not use Computer Use, desktop automation, browser automation, GUI apps, or MCP tools to run this skill.

## Workflow

1. Use `scripts/ai_daily_radar.py` unless the user asks for custom analysis.
2. Keep the run lightweight: no HTML, no login-gated sources. Email is optional through SMTP only.
3. Prefer official APIs and public RSS/JSON endpoints over brittle scraping.
4. Produce exactly 10 items unless the user asks for a different count.
5. In the final response, include the report path and the 10 titles with Chinese title translations.

## Report Format

Each item should contain:

- Original title
- Chinese title translation
- Source name
- URL
- Heat signal, such as points, comments, upvotes, stars, or source priority
- Plain Chinese content summary that does not repeat the title or use labels like "essence" / "core information"; briefly explain uncommon terms, acronyms, tools, benchmarks, or model names when they appear

## Source Strategy

Use a broad AI scope. Do not restrict the report to models only. Include:

- New models and capability releases
- Open-source AI projects
- Developer tools, agents, RAG, Model Context Protocol (MCP as a news topic only), inference, and deployment
- Papers and research breakthroughs
- Official company/lab announcements
- Product and market signals
- Safety, policy, legal, and commercial infrastructure updates

Default source families:

1. Reddit: r/LocalLLaMA
2. Reddit: r/MachineLearning
3. Hacker News
4. Hugging Face Daily Papers
5. Hugging Face model and paper pages when available through public feeds/pages
6. arXiv cs.AI, cs.CL, cs.LG
7. GitHub Trending/Search
8. Official blogs for OpenAI, Anthropic, Google DeepMind, Meta AI, Mistral, DeepSeek, Qwen
9. Product Hunt AI where public pages are accessible
10. AI newsletters and curated feeds such as TLDR AI, Ben's Bites, The Rundown AI, AlphaSignal, when public feeds are accessible

## Scoring Heuristic

Rank candidates with a simple weighted score:

- Recency: published or observed within the last 48 hours
- Heat: comments, points, votes, stars, or upvotes
- Source quality: official source and respected technical community posts score higher
- Builder relevance: practical impact for developers, AI product builders, or technical founders
- Novelty: new release, benchmark, project, method, or controversy

Downrank duplicates, thin marketing posts, generic listicles, and items with no clear developer relevance.

## Scheduled Use

For a Codex automation, schedule a daily heartbeat at 11:00 and prompt:

```text
Run this exact local Python script from a shell only; do not use Computer Use, Browser, Chrome, GUI automation, or MCP tools:
python3 /Users/chenmingjun/.codex/skills/ai-daily-radar/scripts/ai_daily_radar.py --config /Users/chenmingjun/.codex/skills/ai-daily-radar/templates/config.example.json --send-email

Then reply in this thread with the output path, email status, and the 10 titles.
```

## QQ Mail Delivery

Email delivery is optional and disabled by default. Do not write QQ authorization codes into the skill files.

Required environment variables:

```bash
export AI_DAILY_RADAR_SEND_EMAIL=1
export AI_DAILY_RADAR_QQ_USER="your-qq-number@qq.com"
export AI_DAILY_RADAR_QQ_AUTH_CODE="your-qq-mail-smtp-authorization-code"
export AI_DAILY_RADAR_EMAIL_TO="recipient@qq.com"
```

For scheduled Codex runs, prefer a private env file at `~/.codex/ai-daily-radar-email.env`:

```bash
AI_DAILY_RADAR_SEND_EMAIL=1
AI_DAILY_RADAR_QQ_USER=your-qq-number@qq.com
AI_DAILY_RADAR_QQ_AUTH_CODE=your-qq-mail-smtp-authorization-code
AI_DAILY_RADAR_EMAIL_TO=recipient@qq.com
```

Run with email:

```bash
python3 scripts/ai_daily_radar.py --config templates/config.example.json --send-email
```

QQ Mail SMTP defaults live in `templates/config.example.json`:

- Host: `smtp.qq.com`
- Port: `465`
- SSL: enabled

Use the QQ Mail SMTP authorization code, not the QQ login password.
