---
title: Web Tools
description: WebFetch, WebSearch, and Playwright tools
---

Web tools are **disabled by default**. Enable them in **Settings → Network Access**.

Even when enabled, write-capable tools (Playwright) still require permission approval in `ask` mode.

---

## WebFetch

Fetches a URL and returns the page content as Markdown.

```json
{"tool": "WebFetch", "input": {"url": "https://docs.python.org/3/library/asyncio.html"}}
```

HTML is converted to Markdown for a compact representation. Useful for reading documentation, API references, or any public web page.

---

## WebSearch

Searches the web and returns a list of results with titles, URLs, and snippets.

```json
{"tool": "WebSearch", "input": {"query": "python asyncio gather vs wait"}}
```

Returns up to 10 results. Each result includes title, URL, and a short description.

---

## Playwright

Controls a headless Chromium browser for JavaScript-rendered pages, form submission, or UI testing.

```json
{
  "tool": "Playwright",
  "input": {
    "action": "navigate",
    "url": "https://example.com"
  }
}
```

Supported actions: `navigate`, `click`, `type`, `screenshot`, `get_text`, `evaluate`.

### Installing the browser

The first time you use Playwright, install the Chromium binary:

```bash
.venv/bin/playwright install chromium
```

Or from the app: send `{"type": "install_browsers"}` via the sidecar protocol.
