import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Where the API (EMAIL_OUTBOX_DIR, development only) mirrors every outgoing email as a JSON
 * file, so a journey can read the verification link. One folder per API port.
 */
export const EMAIL_OUTBOX_DIR = join(tmpdir(), `agentnest-e2e-outbox-${process.env.E2E_API_PORT ?? "8000"}`);
