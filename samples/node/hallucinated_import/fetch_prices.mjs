/**
 * Scrape product prices from a list of URLs.
 *
 * SEEDED FAILURE — hallucinated-import.
 *
 * 'axios-scraper' is not on npm: it's a conflation of axios and a scraping
 * lib — the exact fabricated-name pattern slopsquatting attackers register
 * (38% of hallucinated names are conflations of two real packages).
 * Expected catch: checkpoint.static.imports (npm registry 404), backed up by
 * tsc TS2307 and, at runtime, ERR_MODULE_NOT_FOUND.
 */
import { scrape } from "axios-scraper";

export async function fetchPrices(urls) {
  const pages = await Promise.all(urls.map((url) => scrape(url, { selector: ".price" })));
  return {
    prices: pages.map((p) => Number.parseFloat(p.text)),
    source: urls[0],
  };
}
