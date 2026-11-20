// Offline rasterization, using the existing development browser. No runtime dependency.
import { chromium } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  for (const app of ["frontend", "landing"]) {
    const directory = `${root}/${app}/public`;
    for (const [name, source, width, height] of [
      ["favicon-32.png", "icon-source", 32, 32],
      ["apple-touch-icon.png", "icon-source", 180, 180],
      ["icon-192.png", "icon-source", 192, 192],
      ["icon-512.png", "icon-source", 512, 512],
      ["app-icon-1024.png", "icon-source", 1024, 1024],
      ["icon-maskable-512.png", "maskable-source", 512, 512],
      ["social-card.png", "social-source", 1200, 630],
    ]) {
      await page.setViewportSize({ width, height });
      const svg = await readFile(`${directory}/brand/${source}.svg`, "utf8");
      await page.setContent(`<style>html,body{margin:0;width:100%;height:100%}svg{display:block;width:100%;height:100%}</style>${svg}`);
      await page.screenshot({ path: `${directory}/${name}`, scale: "css" });
    }
  }
} finally {
  await browser.close();
}
