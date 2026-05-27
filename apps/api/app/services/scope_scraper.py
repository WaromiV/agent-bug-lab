"""
Immunefi scope page scraper — deterministic extraction of bounty program
scope data using Playwright MCP or standalone Playwright.

Usage (standalone):
    python -m app.services.scope_scraper stacks
    python -m app.services.scope_scraper https://immunefi.com/bug-bounty/optimism/scope

Usage (from prepare_service or CLI):
    from app.services.scope_scraper import scrape_scope
    data = await scrape_scope("stacks")  # or full URL

Output: dict with keys:
    program_name, categories (list of {name, assets}),
    impacts_body, severity_tiers (list of {category, severity, qualifiers}),
    out_of_scope_program, out_of_scope_default
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


# ── JS: full scope extraction (runs in Playwright page context) ──────

JS_EXTRACT_ALL = r"""
() => {
  const scope = document.querySelector('main article');
  if (!scope) return JSON.stringify({error: 'no main article'});
  const text = scope.innerText;
  const result = {
    program_name: '',
    impacts_body: '',
    severity_tiers: [],
    out_of_scope_program: [],
    out_of_scope_default: [],
    assets: [],
  };

  // ── PROGRAM NAME ──
  const h1 = document.querySelector('h1');
  if (h1) result.program_name = h1.textContent.trim();

  // ── IMPACTS BODY ──
  const ibStart = text.indexOf('Impacts Body');
  if (ibStart >= 0) {
    let ibText = text.substring(ibStart + 'Impacts Body'.length);
    const nextSection = ibText.search(/\n(Critical|High|Medium|Low)\s*\n/);
    if (nextSection > 0) ibText = ibText.substring(0, nextSection);
    result.impacts_body = ibText.trim();
  }

  // ── SEVERITY TIERS ──
  // Page renders: category header → severity levels → qualifiers.
  // After "View rewards" or "Out of scope" the page re-renders a
  // duplicate impacts table — stop before that.
  const impactsStart = text.indexOf('Impacts in Scope');
  const viewRewards = text.indexOf('View rewards');
  const outOfScopeIdx = text.indexOf('Out of scope');
  const tiersEnd = Math.min(
    viewRewards > impactsStart ? viewRewards : Infinity,
    outOfScopeIdx > impactsStart ? outOfScopeIdx : Infinity
  );

  if (impactsStart >= 0) {
    const tiersText = text.substring(impactsStart, tiersEnd < Infinity ? tiersEnd : undefined);
    const lines = tiersText.split('\n').map(l => l.trim()).filter(l => l);

    const categoryHeaders = ['Blockchain', 'Smart Contracts', 'Smart Contract', 'sBTC',
      'Websites and Applications', 'Blockchain/DLT'];
    const severityLevels = ['Critical', 'High', 'Medium', 'Low', 'Informational'];
    const skipPrefixes = ['Impacts in Scope', 'Impacts Body', 'Impacts',
      'Please note that', 'Please review open', 'Only the following',
      'Select the category'];

    let currentCategory = 'General';
    let currentSeverity = null;
    let currentQualifiers = [];

    function flush() {
      if (currentSeverity && currentQualifiers.length > 0) {
        result.severity_tiers.push({
          category: currentCategory,
          severity: currentSeverity,
          qualifiers: [...currentQualifiers]
        });
      }
      currentQualifiers = [];
    }

    for (const line of lines) {
      if (skipPrefixes.some(p => line.startsWith(p))) continue;
      if (line === 'View rewards' || line === 'Out of scope') break;

      // Category header
      const catMatch = categoryHeaders.find(c => line === c || line === c + ':');
      if (catMatch) { flush(); currentCategory = catMatch.replace(/:$/, ''); currentSeverity = null; continue; }

      // Severity level
      const sevMatch = severityLevels.find(s => line === s || line === s + ':');
      if (sevMatch) { flush(); currentSeverity = sevMatch; continue; }

      // Qualifier — skip noise
      if (currentSeverity && line.length > 10 && !line.startsWith('Attacks are restricted to')) {
        currentQualifiers.push(line);
      }
    }
    flush();

    // Deduplicate: the page renders tiers in a text section AND a
    // bottom table; tab switching can also cause cross-category
    // leakage. Dedupe by qualifier text regardless of category —
    // if the exact same qualifier appeared under a different
    // category already, it's a duplicate rendering artifact.
    const seenQualifiers = new Set();
    result.severity_tiers = result.severity_tiers.filter(t => {
      const key = t.severity + '|' + t.qualifiers.join('|');
      if (seenQualifiers.has(key)) return false;
      seenQualifiers.add(key);
      return true;
    });
  }

  // ── ASSETS ──
  // Extract all GitHub/contract links from the scope section
  const assetLinks = scope.querySelectorAll('a[href*="github.com"], a[href*="etherscan"], a[href*="arbiscan"], a[href*="polygonscan"], a[href*="bscscan"], a[href*="basescan"], a[href*="gnosisscan"], a[href*="ftmscan"], a[href*="celoscan"], a[href*="snowtrace"], a[href*="explorer."]');
  const seenUrls = new Set();
  assetLinks.forEach(a => {
    const url = a.href.replace(/\?utm_source=immunefi$/, '');
    // Skip duplicates and nav links (issues/pulls pages)
    if (seenUrls.has(url)) return;
    if (url.endsWith('/issues') || url.endsWith('/pulls')) return;
    seenUrls.add(url);

    // Walk up to find the row with name/date
    let row = a;
    for (let i = 0; i < 6; i++) {
      if (!row.parentElement) break;
      row = row.parentElement;
      if (row.children.length >= 3) break;
    }
    const rowText = row.innerText.split('\n').map(s => s.trim()).filter(s => s);

    let name = '';
    let addedOn = '';
    for (const t of rowText) {
      if (t.match(/^\d+ \w+ \d{4}$/)) { addedOn = t; continue; }
      if (t.match(/github\.com|scan\.|explorer\./)) continue;
      if (['Target', 'Name', 'Added on'].includes(t)) continue;
      if (!name && t.length > 3 && t.length < 200) name = t;
    }
    result.assets.push({ url, name: name || url.split('/').pop(), added_on: addedOn });
  });

  // ── OUT OF SCOPE — Program ──
  const oosMatch = text.match(/Program's Out of Scope information\n([\s\S]*?)(?=Default Out of Scope|$)/);
  if (oosMatch) {
    result.out_of_scope_program = oosMatch[1].trim().split('\n')
      .map(s => s.trim()).filter(s => s.length > 0);
  }

  // ── OUT OF SCOPE — Default ──
  const defMatch = text.match(/Default Out of Scope and rules\n([\s\S]*?)(?=Submit a Bug|Total Assets|$)/);
  if (defMatch) {
    const sec = defMatch[1].trim();
    const allCat = sec.match(/All categories\n([\s\S]*?)$/);
    result.out_of_scope_default = (allCat ? allCat[1] : sec)
      .split('\n').map(s => s.trim()).filter(s => s.length > 0);
  }

  return JSON.stringify(result, null, 2);
}
"""


# ── Python: standalone runner using Playwright ───────────────────────

async def scrape_scope(target: str) -> dict[str, Any]:
    """Scrape an Immunefi scope page. `target` is either a program slug
    (e.g. 'stacks') or a full URL."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    if target.startswith("http"):
        url = target
    else:
        url = f"https://immunefi.com/bug-bounty/{target}/scope/#top"

    async with async_playwright() as p:
        _exe = p.chromium.executable_path  # full chromium-* that's actually on disk
        browser = await p.chromium.launch(headless=True, executable_path=_exe)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Immunefi analytics keep the network busy; networkidle never settles.
        # Wait for the scope content to render instead.
        await page.wait_for_timeout(5000)

        # Collect assets from EACH category tab. The page only shows
        # one tab's assets at a time, so we click each tab, extract
        # assets, then merge.
        all_assets = []
        tab_names = []

        # First pass: extract assets from the default (first) tab
        first_assets = await page.evaluate("""() => {
          const scope = document.querySelector('main article');
          if (!scope) return '[]';
          const btns = Array.from(scope.querySelectorAll('button'));
          const active = btns.find(b => b.textContent.includes('Selected view'));
          const catName = active ? active.textContent.split('\\n')[0].trim().replace('Selected view','').trim() : 'Unknown';
          const links = scope.querySelectorAll('a[href*="github.com"], a[href*="etherscan"]');
          const seen = new Set();
          const assets = [];
          links.forEach(a => {
            const url = a.href.replace(/\\?utm_source=immunefi$/, '');
            if (seen.has(url) || url.endsWith('/issues') || url.endsWith('/pulls')) return;
            seen.add(url);
            let row = a;
            for (let i = 0; i < 6; i++) { if (!row.parentElement) break; row = row.parentElement; if (row.children.length >= 3) break; }
            const rowText = row.innerText.split('\\n').map(s => s.trim()).filter(s => s);
            let name = '', addedOn = '';
            for (const t of rowText) {
              if (t.match(/^\\d+ \\w+ \\d{4}$/)) { addedOn = t; continue; }
              if (t.match(/github\.com|scan\.|explorer\./)) continue;
              if (['Target', 'Name', 'Added on'].includes(t)) continue;
              if (!name && t.length > 3 && t.length < 200) name = t;
            }
            assets.push({url, name: name || url.split('/').pop(), added_on: addedOn, category: catName});
          });
          return JSON.stringify({category: catName, assets});
        }""")
        first = json.loads(first_assets)
        tab_names.append(first.get("category", ""))
        all_assets.extend(first.get("assets", []))

        # Click remaining tabs and extract their assets
        for _ in range(5):  # max 5 tabs
            clicked = await page.evaluate("""() => {
              const btns = Array.from(document.querySelectorAll('main article button'));
              const next = btns.find(b => b.textContent.includes('Select to change view'));
              if (!next) return false;
              next.click();
              return true;
            }""")
            if not clicked:
                break
            await page.wait_for_timeout(1500)
            tab_assets = await page.evaluate("""() => {
              const scope = document.querySelector('main article');
              if (!scope) return '{"category":"","assets":[]}';
              const btns = Array.from(scope.querySelectorAll('button'));
              const active = btns.find(b => b.textContent.includes('Selected view'));
              const catName = active ? active.textContent.split('\\n')[0].trim().replace('Selected view','').trim() : 'Unknown';
              const links = scope.querySelectorAll('a[href*="github.com"], a[href*="etherscan"]');
              const seen = new Set();
              const assets = [];
              links.forEach(a => {
                const url = a.href.replace(/\\?utm_source=immunefi$/, '');
                if (seen.has(url) || url.endsWith('/issues') || url.endsWith('/pulls')) return;
                seen.add(url);
                let row = a;
                for (let i = 0; i < 6; i++) { if (!row.parentElement) break; row = row.parentElement; if (row.children.length >= 3) break; }
                const rowText = row.innerText.split('\\n').map(s => s.trim()).filter(s => s);
                let name = '', addedOn = '';
                for (const t of rowText) {
                  if (t.match(/^\\d+ \\w+ \\d{4}$/)) { addedOn = t; continue; }
                  if (t.match(/github\.com|scan\.|explorer\./)) continue;
                  if (['Target', 'Name', 'Added on'].includes(t)) continue;
                  if (!name && t.length > 3 && t.length < 200) name = t;
                }
                assets.push({url, name: name || url.split('/').pop(), added_on: addedOn, category: catName});
              });
              return JSON.stringify({category: catName, assets});
            }""")
            tab = json.loads(tab_assets)
            cat = tab.get("category", "")
            if cat in tab_names:
                break  # looped back to first tab
            tab_names.append(cat)
            all_assets.extend(tab.get("assets", []))

        # Now extract everything else (tiers, out-of-scope)
        raw = await page.evaluate(JS_EXTRACT_ALL)
        await browser.close()

        # Merge: replace the JS-extracted assets with our multi-tab collection
        result = json.loads(raw)
        # Dedupe assets by URL
        seen_urls: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for a in all_assets:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                deduped.append(a)
        result["assets"] = deduped
        result["_tab_categories"] = tab_names
        return result


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.services.scope_scraper <slug_or_url>")
        sys.exit(1)
    target = sys.argv[1]
    data = asyncio.run(scrape_scope(target))
    print(json.dumps(data, indent=2))


# ── JS: paginated asset extraction (handles multi-page scope) ────────

JS_EXTRACT_ASSETS_PAGE = r"""
() => {
  const scope = document.querySelector('main article');
  if (!scope) return JSON.stringify([]);
  // Take EVERY anchor in the scope article and exclude only immunefi's own
  // nav/submission links. This is chain-agnostic: it catches aptoscan,
  // tonviewer, tronscan, suiscan, blockscout, layerzeroscan, etc. without a
  // per-chain whitelist (which silently drops assets on unlisted chains).
  const links = scope.querySelectorAll('a[href]');
  const seen = new Set();
  const assets = [];
  links.forEach(a => {
    let url = a.href.replace(/\?utm_source=immunefi.*$/, '').replace(/#.*$/, '');
    let host = '';
    try { host = new URL(a.href).hostname; } catch (e) { return; }
    // Skip immunefi's own pages, in-page anchors, and repo nav tabs.
    if (host.endsWith('immunefi.com')) return;
    if (!a.href.startsWith('http')) return;
    if (seen.has(url) || url.endsWith('/issues') || url.endsWith('/pulls')) return;
    seen.add(url);
    let row = a;
    for (let i = 0; i < 6; i++) {
      if (!row.parentElement) break;
      row = row.parentElement;
      if (row.children.length >= 3) break;
    }
    const rowText = row.innerText.split('\n').map(s => s.trim()).filter(s => s);
    let name = '', addedOn = '';
    for (const t of rowText) {
      if (t.match(/^\d+ \w+ \d{4}$/)) { addedOn = t; continue; }
      if (t.match(/github\.com|scan\.|explorer\./)) continue;
      if (['Target', 'Name', 'Added on'].includes(t)) continue;
      if (!name && t.length > 3 && t.length < 200) name = t;
    }
    assets.push({ url, name: name || url.split('/').pop(), added_on: addedOn });
  });
  return JSON.stringify(assets);
}
"""

JS_CLICK_NEXT_PAGE = r"""
(pageNum) => {
  const scope = document.querySelector('main article');
  if (!scope) return false;
  const btn = Array.from(scope.querySelectorAll('button')).find(
    b => b.textContent.trim() === String(pageNum)
  );
  if (!btn) return false;
  btn.click();
  return true;
}
"""

JS_GET_TOTAL_ASSETS = r"""
() => {
  const scope = document.querySelector('main article');
  if (!scope) return 0;
  const m = scope.innerText.match(/Total Assets in Scope\s*(\d+)/);
  return m ? parseInt(m[1]) : 0;
}
"""


async def scrape_scope_full(target: str) -> dict[str, Any]:
    """Full scope scrape with pagination support. Use this instead of
    scrape_scope for programs with many assets (e.g., The Graph has 35+
    contracts across 3 pages)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")

    if target.startswith("http"):
        url = target
    else:
        url = f"https://immunefi.com/bug-bounty/{target}/scope/#top"

    async with async_playwright() as p:
        _exe = p.chromium.executable_path  # full chromium-* that's actually on disk
        browser = await p.chromium.launch(headless=True, executable_path=_exe)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Immunefi analytics keep the network busy; networkidle never settles.
        # Wait for the scope content to render instead.
        await page.wait_for_timeout(5000)

        total_stated = await page.evaluate(JS_GET_TOTAL_ASSETS)

        # Click "Show all" if present — some programs paginate assets
        # behind this button (e.g., The Graph has 35 contracts hidden).
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const showAll = btns.find(b => b.textContent.trim() === 'Show all');
            if (showAll) { showAll.scrollIntoView(); showAll.click(); }
        }""")
        await page.wait_for_timeout(2000)

        # Collect assets from all pages of all category tabs
        all_assets: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        tabs_clicked: list[str] = []

        for tab_round in range(5):
            # Extract current tab name
            tab_name = await page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('main article button'));
                const active = btns.find(b => b.textContent.includes('Selected view'));
                return active ? active.textContent.split('\\n')[0].trim().replace('Selected view','').trim() : 'Default';
            }""")
            if tab_name in tabs_clicked:
                break
            tabs_clicked.append(tab_name)

            # Paginate through all pages of this tab
            for page_num in range(1, 50):
                if page_num > 1:
                    clicked = await page.evaluate(JS_CLICK_NEXT_PAGE, page_num)
                    if not clicked:
                        break
                    await page.wait_for_timeout(2000)

                page_assets_raw = await page.evaluate(JS_EXTRACT_ASSETS_PAGE)
                page_assets = json.loads(page_assets_raw)
                new_count = 0
                for a in page_assets:
                    if a["url"] not in seen_urls:
                        seen_urls.add(a["url"])
                        a["category"] = tab_name
                        all_assets.append(a)
                        new_count += 1
                if new_count == 0 and page_num > 1:
                    break

            # Click next category tab
            switched = await page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('main article button'));
                const next = btns.find(b => b.textContent.includes('Select to change view'));
                if (!next) return false;
                next.click();
                return true;
            }""")
            if not switched:
                break
            await page.wait_for_timeout(1500)

        # Extract tiers + out-of-scope (these don't paginate)
        scope_raw = await page.evaluate(JS_EXTRACT_ALL)
        await browser.close()

    result = json.loads(scope_raw)
    result["assets"] = all_assets
    result["_total_stated"] = total_stated
    result["_tabs"] = tabs_clicked
    return result
