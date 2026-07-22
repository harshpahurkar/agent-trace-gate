/** Contract for samples/node/schema_mismatch/invoice.mjs. */
import { z } from "zod";

export const entrypoint = "formatInvoice";
export const args = [
  [
    { price: 442.48, qty: 3 },
  ],
];
export const schema = z.object({
  total: z.number(),
  itemCount: z.number().int(),
});
