import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

/** Re-create the demo users and workspaces so every run starts from the same data. */
export default function globalSetup(): void {
  const backendDir = fileURLToPath(new URL("../../backend", import.meta.url));
  execFileSync("uv", ["run", "python", "-m", "app.cli", "seed", "--reset"], {
    cwd: backendDir,
    stdio: "inherit",
  });
}
