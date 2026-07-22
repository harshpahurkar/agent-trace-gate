/**
 * Format an invoice for the billing API.
 *
 * SEEDED FAILURE — schema-mismatch.
 *
 * Runs clean end to end, but `total` comes back as a locale-formatted string
 * ("1,499.00") where the contract demands z.number(). Static analysis can't
 * see it, the smoke run doesn't throw — only the zod contract checkpoint
 * catches the drift. The classic "looks right in review" bug.
 */
export function formatInvoice(items) {
  const subtotal = items.reduce((sum, it) => sum + it.price * it.qty, 0);
  const total = subtotal * 1.13;
  return {
    total: total.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    itemCount: items.length,
  };
}
