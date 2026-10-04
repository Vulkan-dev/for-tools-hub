# RAW LEAKS

**AUTOMATION TOOLKIT**

---

RAW LEAKS is a Windows-first command line toolkit that joins Discord servers
straight from an invite link. Point it at a `discord.gg` URL, load your
accounts once, and every account is logged in, verified and fired at the
invite one at a time, with randomised pacing between requests.

The project is built as a single, focused tool: no dashboard, no database, no
extra moving parts. Everything you need is a token list, a config file and one
command.

---

## Features

- **Invite link ingestion** — accepts full URLs (`discord.gg/…`,
  `discord.com/invite/…`, `discord.com/join/…`) and bare invite codes.
- **Invite pre-check** — the link is resolved before the first join, so a dead
  invite costs one request instead of one per account.
- **Multi-account login** — every account in `tokens.txt` is authenticated and
  brought online before the first join fires, with a stagger between logins.
- **Sequential, jittered joins** — accounts are joined one after another with a
  random delay added to the base stagger, so the run never repeats a fixed
  interval.
- **Rate limit protection** — normal Discord 429s are waited out automatically;
  long blocks and Cloudflare limits stop the run instead of pushing harder.
- **Per-account budget** — a daily join cap, a minimum gap between two joins by
  the same account and a global cooldown after repeated failures.
- **Account quarantine** — locked, restricted or verification-walled accounts
  are dropped from the session rather than retried.
- **Optional per-account proxy** — attach a proxy to individual accounts
  directly in the token list.
- **Automatic CAPTCHA solving** — Discord join challenges are routed through
  the NopeCHA hook instead of crashing the run.
- **Branded, scannable logs** — every line carries the `[RAW LEAKS]` prefix and
  a fixed-width `INFO / OK / WARN / ERROR` severity label.
- **Windows terminal aware** — UTF-8 console setup, ANSI colour detection and
  an ASCII banner fallback for terminals with limited Unicode support.
- **Non-interactive mode** — `--invite`, `--stagger` and `--yes` make the
  toolkit easy to script and schedule.
- **Session reuse** — accounts stay online, so you can join several invites in
  one session without logging in again.

---

## Installation

Requires **Python 3.10+** (64-bit Windows builds are recommended).

```bat
git clone https://github.com/Vulkan-dev/for-tools-hub.git
cd for-tools-hub

py -3 -m pip install -r requirements.txt
```

Copy the token template and add your accounts:

```bat
copy tokens.example.txt tokens.txt
notepad tokens.txt
```

`tokens.txt` is ignored by git on purpose — real accounts are never committed.

---

## Windows usage

### Launcher

Double-click **`run.bat`**, or run it from a terminal:

```bat
run.bat
```

The launcher switches the console to UTF-8, picks `py -3` (or `python`) from
`PATH`, and keeps the window open when it was started by double-clicking.

### Interactive session

```bat
python main.py
```

Paste an invite at the prompt — nothing is stored, the toolkit always asks.
Accounts are logged in once; from then on you can keep joining invites until
you answer `n`.

### One-shot runs

```bat
python main.py --invite https://discord.gg/example
python main.py --invite example --stagger 250 --yes
python main.py --tokens accounts.txt --timeout 90 --invite example --yes
```

### Terminal options

| Flag | Effect |
| --- | --- |
| `--ascii` | Render the banner with plain ASCII instead of box drawing characters |
| `--no-color` | Disable ANSI colour output |
| `--version` | Print `RAW LEAKS — Automation Toolkit` and the version |
| `-h`, `--help` | Full usage reference |

Environment equivalents: `RAW_LEAKS_ASCII=1` forces the ASCII banner,
`NO_COLOR=1` disables colour.

---

## Configuration

Settings live in `config.json` next to `main.py`. There is no stored invite.

```json
{
  "stagger_ms": 1500,
  "stagger_jitter_ms": 1000,
  "ready_timeout_seconds": 60,
  "tokens_file": "tokens.txt",
  "captcha_url": "https://discord.com/channels/@me",
  "nopecha_key": "",
  "nopecha_url": "https://api.nopecha.com",
  "safety": {
    "enabled": true,
    "login_stagger_ms": 1000,
    "min_gap_seconds": 60,
    "max_joins_per_account": 5,
    "max_consecutive_failures": 3,
    "cooldown_seconds": 120,
    "max_ratelimit_timeout": 120,
    "ratelimit_retries": 3,
    "verify_invite": true
  }
}
```

| Key | Description |
| --- | --- |
| `stagger_ms` | Base delay between two join requests, clamped to `0`–`60000` |
| `stagger_jitter_ms` | Random extra delay (up to this value) added to every stagger, clamped to `0`–`60000` |
| `ready_timeout_seconds` | How long to wait for Discord's READY event (clamped to `5`–`300`) |
| `tokens_file` | Token list, one account per line |
| `captcha_url` | Where Discord serves the join CAPTCHA challenge |
| `nopecha_key` | NopeCHA API key used to solve join CAPTCHAs |
| `nopecha_url` | NopeCHA API base URL |

`safety` block:

| Key | Description |
| --- | --- |
| `enabled` | `false` turns off every pacing rule below (the joins themselves are unchanged) |
| `login_stagger_ms` | Delay between two account logins |
| `min_gap_seconds` | Minimum time between two joins by the same account |
| `max_joins_per_account` | Daily join budget per account, stored in `state.json` |
| `max_consecutive_failures` | Failures in a row before the whole run pauses |
| `cooldown_seconds` | Length of that pause |
| `max_ratelimit_timeout` | Longest a single request may stay blocked before the run gives up (library waits up to this long, then raises) |
| `ratelimit_retries` | Join attempts allowed after a rate limit before that account is left alone |
| `verify_invite` | Resolve the invite once, before the first join |

Environment variables override the file:

| Variable | Overrides |
| --- | --- |
| `NOPECHA_KEY` | `nopecha_key` |
| `RAW_LEAKS_STAGGER_MS` | `stagger_ms` |
| `RAW_LEAKS_TOKENS_FILE` | `tokens_file` |

### Token file format

```text
# comments are ignored
mfa.example-token-value                 # main
mfa.example-token-value | http://user:pass@host:8080   # target
another-user-token                      # alt
```

Everything after the first `#` on an account line becomes the label shown in
the logs (labels default to `#1`, `#2`, …). An optional proxy can be added
before the label, separated by `|`; supported schemes are `http://`,
`https://`, `socks4://` and `socks5://`. The proxy applies to that account
only.

---

## Rate limits and account safety

Automated joins come with real risk: Discord rate limits invites per account,
per route and per IP, and repeated pressure shows up as Cloudflare blocks,
join locks or account flags. RAW LEAKS is built to stay on the safe side of
those limits:

- accounts log in with a stagger instead of all at once
- joins run **one at a time**, in randomised order, with jitter on the delay
- the invite is validated once up front, not once per account
- a normal `429` is absorbed by the HTTP layer; a long or Cloudflare block
  stops the run and tells you to wait
- each account has a daily budget (`state.json`) and a minimum gap between
  two joins, so a session can never quietly turn into a join flood
- accounts that come back locked, restricted or verification-walled are
  removed from the session instead of being retried
- a run of consecutive failures pauses everything for `cooldown_seconds`

Honest limits: **no tool can guarantee zero rate limits, zero bans and zero
flags.** These rules reduce pressure and stop early when Discord pushes back;
they do not make an automated account invisible, and they cannot undo
enforcement that has already happened. Keep `stagger_ms`, `min_gap_seconds`
and `max_joins_per_account` conservative, and leave headroom between runs.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Python 3 was not found on PATH` | Install Python from python.org and tick **Add python.exe to PATH**, then reopen the terminal. |
| Banner shows `?` or garbled boxes | Run through `run.bat`, or execute `chcp 65001` before starting. Use `--ascii` on terminals that cannot render Unicode. |
| Colours missing | Expected when output is piped or `NO_COLOR` is set. Use a terminal with VT support (Windows Terminal, cmd on Windows 10+). |
| `No accounts found in tokens.txt` | Create the file (the toolkit generates it from `tokens.example.txt`) and add one token per line. |
| `login failed: Improper token has been passed` | The token is expired or truncated — export a fresh one. |
| `No accounts came online - nothing to join with` | Raise `ready_timeout_seconds` or `--timeout`; check the network and the `ERROR` lines above it. |
| `No NopeCHA key set` warning | Join challenges cannot be solved. Put your key in `config.json` (`nopecha_key`) or set `NOPECHA_KEY`. |
| `already in this server` | That account is already a member — counted as `already`, the run continues with the rest. |
| `rate limited - backing off` | Normal; the toolkit waits and retries. Raise `stagger_ms` and lower `stagger_jitter_ms` if it repeats. |
| `hit a Cloudflare rate limit … stopping the run` | Intentional stop. Wait before starting again; raise `stagger_ms` / `min_gap_seconds` for the next run. |
| `skipped - daily join limit of 5 reached` | The account hit `max_joins_per_account` today — delete `state.json` only if you accept the risk. |
| `removed from this session` | The account is restricted or locked. Do not push it; verify or restore it manually first. |
| Proxy errors at login | Check the proxy scheme and credentials in `tokens.txt` — only one proxy per account, separated by `\|`. |

---

## Development

Project layout:

```text
raw-leaks-joiner/
├── main.py                 entry point
├── run.bat                 Windows launcher
├── config.json             runtime settings (includes the safety block)
├── tokens.example.txt      token list template
├── requirements.txt
└── raw_leaks/
    ├── __init__.py         brand constants and version
    ├── banner.py           startup banner (Unicode + ASCII fallback)
    ├── logger.py           [RAW LEAKS] INFO / OK / WARN / ERROR output
    ├── console.py          Windows console, colour, encoding, shutdown guard
    ├── config.py           config.json + token/proxy file loading
    ├── invites.py          invite URL and code parsing
    ├── safety.py           rate limit policy and daily budget state
    ├── captcha.py          NopeCHA CAPTCHA solving
    ├── joiner.py           account login and invite join engine
    └── cli.py              argument parsing and session flow
```

Local checks before committing:

```bat
py -3 -m compileall raw_leaks main.py
python main.py --help
python main.py --no-color
```

Brand rules applied everywhere:

- The application name is **RAW LEAKS — Automation Toolkit**.
- Logs always start with `[RAW LEAKS]` followed by a five-character severity
  label (`INFO`, `OK`, `WARN`, `ERROR`).
- Style stays near-black, white and muted grey with a single restrained
  deep-red accent — no gradients, glow, emojis or decorative noise.

---

## Preview

Startup:

```text
╔══════════════════════════════════════════════╗
║                                              ║
║              R A W   L E A K S               ║
║              AUTOMATION TOOLKIT              ║
║                                              ║
╚══════════════════════════════════════════════╝
  RAW LEAKS — Automation Toolkit  v1.0.0
────────────────────────────────────────────────
[RAW LEAKS] Initializing...
[RAW LEAKS] Loading configuration...
[RAW LEAKS] System ready.
```

Run output:

```text
[RAW LEAKS] INFO  Stagger 1500ms (+1000ms) | ready timeout 60s
[RAW LEAKS] INFO  Safety: login 1000ms · 60s gap · 5 joins/account/day
[RAW LEAKS] WARN  No NopeCHA key set - join CAPTCHAs cannot be solved

ACCOUNTS
────────────────────────────────────────────────
  file     tokens.txt
  loaded   3

INVITE
────────────────────────────────────────────────
  link     https://discord.gg/example

[RAW LEAKS] INFO  Logging in 3 account(s) ...
[RAW LEAKS] OK    main online as account_one
[RAW LEAKS] OK    #2 online as account_two
[RAW LEAKS] ERROR #3 login failed: Improper token has been passed
[RAW LEAKS] INFO  Online: 2 | offline: 1
[RAW LEAKS] OK    Invite verified: Example Server
[RAW LEAKS] INFO  Joining invite example with 2 account(s), stagger 1500ms (+1000ms jitter)
[RAW LEAKS] OK    main joined Example Server (4 joins left today)
[RAW LEAKS] INFO  #2 is already in this server

RESULT
────────────────────────────────────────────────
  invite   example
  online   2
  joined   1
  already  1
  failed   0
  skipped  0
```

---

**RAW LEAKS — Automation Toolkit**
