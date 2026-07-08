# Source Adapter — note.com (article sites)

Fetches one paid or free note.com article into a **Fetched Article** (contract:
[adapter_contract.md](adapter_contract.md)). This is the built adapter and the reference shape for other
HTML article sites (Hatena Blog, personal blogs, tournament-report sites) — a future article adapter
mostly changes the selectors and the paywall marker.

## Identify

URL host is `note.com`. Canonical article URL: `https://note.com/<handle>/n/<source_id>` where
`<source_id>` starts with `n` (e.g. `n92a6cd123bc7`). `<handle>` is the author (e.g. `volx_`).

## Fetch — two paths

**Free / fully-public article → `WebFetch` (no browser).** note.com server-renders article bodies, so
for a genuinely free article `WebFetch` retrieves it cleanly with **no browser session needed** — the
simplest path. Prompt it to return the body **verbatim in Japanese** plus an explicit paywall/date
report. Verified 2026-07-08: `WebFetch` returned title/author/date/structure for a public note.com
article without the extension. Follow same-host redirects if returned.

**Paid / authed / repost-gated article → drive the authenticated browser** (below).

⚠️ **note.com "free" is often repost-gated, not account-free.** Many articles use
「途中から有料 … Xでリポストしていただければ無料で読める」 — the back half (usually the payload) is locked unless the
reader **reposts on X**; a mere account does not unlock it, and unauthenticated `WebFetch` sees only the
truncated free intro. The access guard MUST treat a repost/purchase gate as truncation → STOP (see
below). If the free portion is truncated, the working fallback is the **paste path**: the user unlocks
it in their own browser and pastes the full text into `data/strategy/articles/<article_name>/source.txt`
(gitignored), then Synthesis runs on that — same shape as the manual-transcript adapter.

## Fetch (drive the authenticated browser)

You ride the user's **already-logged-in** note.com session — no credentials are handled. Load the core
claude-in-chrome tools in ONE `ToolSearch` call (see the MCP instructions), then:

1. `navigate` to the canonical URL.
2. Extract the rendered article: prefer `get_page_text` / `read_page` for the main `article` body. Strip
   note.com chrome — the header/nav, the author card, "おすすめ" / recommended-articles rail, the comment
   and "スキ" (like) blocks, and the footer. Keep headings, paragraphs, and lists in reading order.
3. Read provenance from the page/metadata: `title` (the `<h1>` / `og:title`, kept in Japanese),
   `handle` and `source_id` (from the URL), `date` (the published date, → `YYYY-MM`), `language` (`ja`).

## Access guard (the load-bearing check)

note.com truncates unpurchased paid articles to a free preview and shows a purchase gate. **Before
declaring the body usable, detect the gate:**

- A purchase/continue block: a "購入手続きへ" / "続きを見る" / "有料" price/paywall region near the cutoff.
- A body that ends abruptly with a "ここから先は" ("from here on…") lead-in into a locked region.
- A suspiciously short body for a paid strategy article (e.g. only the intro renders).

If any is present → set `access = paywalled` (or `truncated`) and **STOP the workflow**: tell the user to
purchase the article or confirm they're logged in. **Do not** synthesize from the preview. Only when the
full body renders end-to-end with no gate → `access = complete`.

## Emit

Save the cleaned body to `data/strategy/raw/<handle>_<slug>.md` (gitignored) and set `raw_path`. Emit the
Fetched Article struct with `source = note_com`, `body_kind = article`. Hand off to Synthesis
([synthesis.md](synthesis.md)) only when `access == complete`.

## Notes

- The user has already purchased each article and only ingests it once — favour a clean single pass over
  retry loops. If the page won't render the full body, the honest outcome is the access STOP, not a
  workaround.
- Japanese body stays Japanese in the raw file; translation/synthesis happens in Synthesis, in English.
