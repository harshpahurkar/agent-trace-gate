/** Contract for samples/node/hallucinated_import/fetch_prices.mjs. */
import { z } from "zod";

export const entrypoint = "fetchPrices";
export const args = [["https://example.com/widgets/42"]];
export const schema = z.object({
  prices: z.array(z.number()),
  source: z.string(),
});
