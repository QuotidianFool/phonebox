# GLDY page for PhoneBox (build #1)

A custom PhoneBox page that shows the state of the gldy lab on the paired phone. This is the first build from
`2026-11-18_phonebox-gldy-surface-plan.md`: four Command widgets, no new code, no cron.

## What it shows

| Widget | Refresh | What it runs |
| --- | --- | --- |
| Paperclip | 60 s | `paperclipai issue list -C <company> --json` → counts of everything not `done`, grouped by status |
| Sparks model | 60 s | the model id served by TensorFold on `127.0.0.1:18888` |
| Brain | 300 s | conversation, knowledge and passage counts from `gldy-brain status` |
| Crons | 120 s | active job count plus the first line of `hermes cron doctor` |

## Files

- `pages/gldy.json` — the page object, ready to insert into the agent's `config.json`.

## Install

1. Stop the agent, or edit `config.json` while it runs (the agent re-reads it on the next request).
2. Back it up: `cp "$HOME/Library/Application Support/PhoneBox/config.json" config.json.bak`.
3. Insert the object from `pages/gldy.json` into the `pages` array — anywhere you want it in the tab order. The
   live Studio install puts it second, right after `home`.
4. Refresh the panel: `curl -X POST http://127.0.0.1:8765/api/refresh` (or Settings → Webhooks → Refresh).

## Why absolute paths

Command widgets run under the agent's environment. If the agent is started by launchd, `PATH` is minimal, so every
binary is called by absolute path: `/Users/gldy/.local/bin/{paperclipai,gldy-brain,hermes}`, `/usr/bin/{jq,curl,grep,head}`.
Change these if the tools live elsewhere.

## Things to know

- `paperclipai issue list` needs the company id. The Studio's company is `gldy lab`,
  `4f94b505-df14-4cff-b431-b2da864262fa`. Discover it with `paperclipai company list`.
- `hermes cron doctor` reports only current problems; the widget prints its first line, so "Cron doctor found 0
  issue(s)" is the healthy state. A `Last failure` line in `hermes cron list` may be historical and recovered.
- The agent's local API on `127.0.0.1:8765` needs no token. The phone-facing LAN port (`8766`) does.

## Next builds

From the plan document, in order: a push script plus a Custom HTML dashboard fed by `POST /api/push/<key>`, notify
rules for stale backups and failed jobs, dictation into the Hermes desktop client, and a shortcut deck for lab actions.

## Upstream

Forked from `ersinkoc/phonebox` at `907965d` (0.9.21). Keep gldy additions in `gldy/` so upstream merges stay clean.
