import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { EMAIL_OUTBOX_DIR } from "./outbox";

/** Re-create the demo users and workspaces so every run starts from the same data. */
export default function globalSetup(): void {
  rmSync(EMAIL_OUTBOX_DIR, { recursive: true, force: true });
  const backendDir = fileURLToPath(new URL("../../backend", import.meta.url));
  execFileSync("uv", ["run", "python", "-m", "app.cli", "seed", "--reset"], {
    cwd: backendDir,
    stdio: "inherit",
  });
}
