# Clodds — AI Trading Terminal for Prediction Markets & Crypto

[![Deploy to Railway](https://railway.app/button.svg)](https://railway.com/deploy/8Qf2_m)

Clodds (Claude + Odds) is a personal AI trading terminal for prediction markets, crypto spot, perpetual futures, and token launches. Chat with your trading agent through a built-in WebChat UI or 21 messaging platforms, trade across 10 prediction markets and 7 futures exchanges, and manage your portfolio — all through natural conversation. Powered by Claude with 118+ trading strategies, whale tracking, arbitrage detection, and copy trading.

## Features

- **WebChat built in**: Claude-style browser interface at `/webchat` — chats, projects, artifacts, unlimited history, context compacting. No third-party dependencies.
- **Multi-platform trading**: Polymarket, Kalshi, Betfair, Manifold, Binance Futures (125x), Bybit, Hyperliquid (100x), on-chain Solana perps via Percolator
- **Solana + EVM DeFi**: Jupiter, Raydium, Orca, Meteora, Pump.fun, Bags.fm; Uniswap V3, 1inch, PancakeSwap, Virtuals on Base, ETH, Arbitrum, Optimism, Polygon
- **AI agents**: 4 specialized agents (Main, Trading, Research, Alerts), 8 LLM providers, 119+ skills, semantic memory via LanceDB
- **Risk engine**: VaR/CVaR, circuit breaker, Kelly sizing, volatility regime detection, daily loss limits, kill switch — defaults to dry-run mode
- **Token launches**: One-call Solana token launches via Meteora bonding curves
- **MCP server**: Expose all 119 skills as MCP tools for Claude Desktop / Claude Code
- **i18n**: 10 languages

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Channels: WebChat (:18789/webchat), Telegram,       │
│  Discord, Slack, WhatsApp, Matrix, +15 more          │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│  Clodds Gateway (Node.js 22, TypeScript)             │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────┐  │
│  │ 4 AI Agents│ │ 119+ Skills  │ │ Risk Engine    │  │
│  │ (Claude +7)│ │ 18 Tools     │ │ (VaR/Kelly/CB) │  │
│  └────────────┘ └──────────────┘ └────────────────┘  │
│  SQLite state + LanceDB memory (/data volume)        │
└──────────────────────┬───────────────────────────────┘
                       │
    ┌──────────────┬───┴──────────┬──────────────┐
    ▼              ▼              ▼              ▼
┌──────────┐ ┌──────────┐ ┌─────────────┐ ┌───────────┐
│ Predict  │ │ Solana   │ │ EVM DeFi    │ │ Futures   │
│ Markets  │ │ DeFi     │ │ (DEXs)      │ │ (CEX/DEX) │
└──────────┘ └──────────┘ └─────────────┘ └───────────┘
```

Single service with an embedded SQLite database — no external database required. All state (chat history, trade ledger, config) lives in the `/data` volume.

## Deploy and Host

Click the deploy button, set `ANTHROPIC_API_KEY` (required) and optionally `CLODDS_TOKEN` / `WEBCHAT_TOKEN` for access control. Railway builds the container from source and starts the gateway on port 18789. A volume is attached at `/data` for persistent state — chat history and trading config survive restarts and redeploys.

## About Hosting

Clodds runs as a single Node.js service with an embedded SQLite database persisted on a Railway volume at `/data`. The gateway exposes:

- `/health` — health endpoint (used by Railway healthchecks)
- `/webchat` — built-in browser chat interface
- HTTP/WebSocket API — full trading + chat API (see upstream `docs/API_REFERENCE.md`)

Trading is **dry-run by default**: add exchange API keys as environment variables when you want live execution. LLM inference calls Anthropic directly from the container, so no inbound webhooks are needed for chat. The container pre-downloads the embedding model at build time so first request is instant.

## Why Deploy

Self-hosting Clodds keeps your API keys, wallet keys, and trading history on infrastructure you control instead of a third-party SaaS. Railway gives you one-click deploys, persistent volumes, private networking, and automatic HTTPS — and the bot's 21 messaging channels and MCP server all work out of the box without extra infrastructure.

## Common Use Cases

- **Personal AI trading assistant**: chat with Claude about markets, get orderbook analysis, execute trades via natural conversation
- **Prediction market arbitrage**: real-time cross-platform spread detection (Polymarket vs Kalshi) with Kelly sizing
- **Portfolio automation**: DCA bots, copy trading, whale tracking across Solana/ETH/Base and more
- **AI agent backend**: run Clodds as an MCP server so Claude Desktop/Code gets 119 trading skills as tools
- **Bittensor mining**: register and mine TAO on Bittensor subnets from the same terminal

## Dependencies for

### Deployment Dependencies

- **Anthropic API key** (required): powers the AI. Get one at https://console.anthropic.com
- No external databases required — SQLite and LanceDB are embedded and persisted on the attached volume
- Optional: Telegram/Discord/Slack bot tokens for messaging channels; exchange API keys for live trading (dry-run by default)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for the AI ([console.anthropic.com](https://console.anthropic.com)) |
| `CLODDS_TOKEN` | No | Secret token for gateway API access |
| `WEBCHAT_TOKEN` | No | Auth token for the WebChat UI |
| `TELEGRAM_BOT_TOKEN` | No | Telegram channel (from [@BotFather](https://t.me/BotFather)) |
| `DISCORD_BOT_TOKEN` / `DISCORD_APP_ID` | No | Discord channel |
| `POLY_*`, `KALSHI_*`, `BINANCE_*`, etc. | No | Exchange credentials for live trading (dry-run until set) |

## Using the Instance

1. Open your Railway deployment domain → `/webchat`
2. Start chatting: "Show me BTC orderbook on Binance", "Find arbitrage between Polymarket and Kalshi", "Set up a $50 weekly DCA into ETH"
3. For Telegram: create a bot via [@BotFather](https://t.me/BotFather), set `TELEGRAM_BOT_TOKEN`, message your bot

> ⚠️ **Trading risk**: Clodds executes real trades only when you add exchange credentials. All strategies default to dry-run mode. Use the built-in risk engine limits (`/risk` in chat) before going live.

## Links

- Upstream: https://github.com/alsk1992/CloddsBot
- Docs: https://github.com/alsk1992/CloddsBot/tree/main/docs
- License: MIT