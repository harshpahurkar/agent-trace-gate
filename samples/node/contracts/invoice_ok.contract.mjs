/** Contract for samples/node/passing/invoice_ok.mjs. */
import { z } from "zod";

export const entrypoint = "computeInvoice";
export const args = [
  [
    { price: 100, qty: 2 },
    { price: 49.5, qty: 1 },
  ],
  0.13,
];
export const schema = z.object({
  subtotal: z.number(),
  tax: z.number(),
  total: z.number(),
  itemCount: z.number().int(),
});
