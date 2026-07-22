/**
 * Turn an article title into a URL slug.
 *
 * SEEDED FAILURE — hallucinated-api.
 *
 * lodash has `kebabCase`; `_.slugify` does not exist. A very plausible
 * hallucination — other ecosystems (Django, Rails) do ship slugify.
 * Expected catch: checkpoint.static.types (tsc TS2339 via @types/lodash) —
 * or, with --skip-static, "TypeError: _.slugify is not a function" recorded
 * on the `code.call makeSlug` span at runtime.
 */
import _ from "lodash";

export function makeSlug(title) {
  return _.slugify(title.trim());
}
