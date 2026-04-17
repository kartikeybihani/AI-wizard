import { gzipSync } from "node:zlib";
import { promises as fs } from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const CHUNKS_DIR = path.join(ROOT, ".next", "static", "chunks");
const HOME_HTML = path.join(ROOT, ".next", "server", "app", "index.html");
const MAX_GZIP_BYTES = 300 * 1024;

async function listFilesRecursive(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = await Promise.all(
    entries.map(async (entry) => {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        return listFilesRecursive(fullPath);
      }
      return fullPath;
    }),
  );
  return files.flat();
}

function includeChunk(filepath) {
  const normalized = filepath.replace(/\\/g, "/");
  if (!normalized.endsWith(".js")) {
    return false;
  }
  return (
    normalized.includes("/chunks/app/") ||
    normalized.includes("/chunks/main-app") ||
    normalized.includes("/chunks/webpack") ||
    normalized.includes("/static/chunks/")
  );
}

async function homeScriptsFromHtml() {
  let html;
  try {
    html = await fs.readFile(HOME_HTML, "utf8");
  } catch {
    return [];
  }

  const matched = [...html.matchAll(/src="\/_next\/static\/chunks\/([^"]+\.js)"/g)];
  const files = matched
    .map(([, name]) => path.join(CHUNKS_DIR, name))
    .filter((filepath) => filepath.startsWith(CHUNKS_DIR));

  const unique = [...new Set(files)];
  const existing = await Promise.all(
    unique.map(async (filepath) => {
      try {
        await fs.access(filepath);
        return filepath;
      } catch {
        return null;
      }
    }),
  );

  return existing.filter(Boolean);
}

async function main() {
  const htmlTargetFiles = await homeScriptsFromHtml();
  const targetFiles =
    htmlTargetFiles.length > 0
      ? htmlTargetFiles
      : (await listFilesRecursive(CHUNKS_DIR)).filter(includeChunk);

  if (!targetFiles.length) {
    throw new Error("No app chunks found for bundle analysis");
  }

  let total = 0;
  for (const file of targetFiles) {
    const source = await fs.readFile(file);
    total += gzipSync(source).byteLength;
  }

  const kb = (total / 1024).toFixed(1);
  const maxKb = (MAX_GZIP_BYTES / 1024).toFixed(0);
  const status = total <= MAX_GZIP_BYTES ? "PASS" : "FAIL";

  console.log(`[bundle-check] ${status} home route JS gzip total: ${kb}KB (budget ${maxKb}KB)`);

  if (total > MAX_GZIP_BYTES) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error("[bundle-check] error", error);
  process.exitCode = 1;
});
