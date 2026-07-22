/** Contract for samples/node/hallucinated_method/slugify.mjs. */
import { z } from "zod";

export const entrypoint = "makeSlug";
export const args = ["Hello World — Agent Edition"];
export const schema = z.string().regex(/^[a-z0-9-]+$/);
