# RAW LEAKS

**AUTOMATION TOOLKIT**

---

RAW LEAKS is a Windows-first command line toolkit that joins Discord servers
straight from an invite link. Point it at a `discord.gg` URL, load your
accounts once, and every account is logged in, verified and fired at the
invite with a controlled stagger between requests.

The project is built as a single, focused tool: no dashboard, no database, no
extra moving parts. Everything you need is a token list, a config file and one
command.

---

## Features

- **Invite link ingestion** — accepts full URLs (`discord.gg/…`,
  `discord.com/invite/…`, `discord.com/join/…`) and bare invite codes.
- **Multi-account login** — every account in `tokens.txt` is authenticated and
  brought online before the first join fires.
- **Staggered joins** — configurable millisecond delay between accounts so the
  run stays predictable under rate limits.
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

Paste an invite at the prompt. Accounts are logged in once; from then on you
can keep joining invites until you answer `n`.

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

Settings live in `config.json` next to `main.py`.

```json
{
  "invite": "",
  "stagger_ms": 10,
  "ready_timeout_seconds": 60,
  "tokens_file": "tokens.txt",
  "captcha_url": "https://discord.com/channels/@me",
  "nopecha_key": "",
  "nopecha_url": "https://api.nopecha.com"
}
```

| Key | Description |
| --- | --- |
| `invite` | Invite used when the interactive prompt is left empty |
| `stagger_ms` | Delay between each account's join request (clamped to `0`–`5000`) |
| `ready_timeout_seconds` | How long to wait for Discord's READY event (clamped to `5`–`300`) |
| `tokens_file` | Token list, one account per line |
| `captcha_url` | Where Discord serves the join CAPTCHA challenge |
| `nopecha_key` | NopeCHA API key used to solve join CAPTCHAs |
| `nopecha_url` | NopeCHA API base URL |

Environment variables override the file:

| Variable | Overrides |
| --- | --- |
| `NOPECHA_KEY` | `nopecha_key` |
| `RAW_LEAKS_INVITE` | `invite` |
| `RAW_LEAKS_STAGGER_MS` | `stagger_ms` |
| `RAW_LEAKS_TOKENS_FILE` | `tokens_file` |

### Token file format

```text
# comments are ignored
mfa.example-token-value          # main
another-user-token               # alt
```

Everything after the first `#` on an account line becomes the label shown in
the logs.

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
| `failed to join …: You are already a guild member` | That account is already in the server — the run continues with the rest. |
| Rate limit messages | Increase `stagger_ms` (for example `250` or `1000`) and run again. |

---

## Development

Project layout:

```text
raw-leaks-joiner/
├── main.py                 entry point
├── run.bat                 Windows launcher
├── config.json             runtime settings
├── tokens.example.txt      token list template
├── requirements.txt
└── raw_leaks/
    ├── __init__.py         brand constants and version
    ├── banner.py           startup banner (Unicode + ASCII fallback)
    ├── logger.py           [RAW LEAKS] INFO / OK / WARN / ERROR output
    ├── console.py          Windows console, colour and encoding setup
    ├── config.py           config.json + token file loading
    ├── invites.py          invite URL and code parsing
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
[RAW LEAKS] Initializing...
[RAW LEAKS] Loading configuration...
[RAW LEAKS] System ready.
```

Run output:

```text
[RAW LEAKS] INFO  RAW LEAKS — Automation Toolkit
[RAW LEAKS] INFO  Version 1.0.0
[RAW LEAKS] INFO  Stagger 10ms | ready timeout 60s
[RAW LEAKS] INFO  Accounts loaded: 3
[RAW LEAKS] INFO  Logging in 3 account(s) ...
[RAW LEAKS] OK    main online as account_one
[RAW LEAKS] OK    #2 online as account_two
[RAW LEAKS] ERROR #3 login failed: Improper token has been passed
[RAW LEAKS] INFO  Online: 2 | offline: 1
[RAW LEAKS] INFO  Joining invite example with 2 account(s) (10ms apart)
[RAW LEAKS] OK    main joined Example Server
[RAW LEAKS] ERROR #2 failed to join example: You are already a guild member
[RAW LEAKS] INFO  Join finished: 1 joined, 1 failed
```

---

**RAW LEAKS — Automation Toolkit**
