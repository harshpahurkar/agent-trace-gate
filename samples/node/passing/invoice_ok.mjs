/**
 * Compute an invoice total with tax.
 *
 * This sample is intentionally CORRECT — the Node control sample. tsc is
 * clean, the smoke run shows a green `code.call computeInvoice` span, and
 * the return value satisfies the zod contract.
 */
export function computeInvoice(items, taxRate) {
  const subtotal = items.reduce((sum, it) => sum + it.price * it.qty, 0);
  const tax = Math.round(subtotal * taxRate * 100) / 100;
  return {
    subtotal,
    tax,
    total: Math.round((subtotal + tax) * 100) / 100,
    itemCount: items.length,
  };
}
