import fs from "node:fs";
import path from "node:path";

import dotenv from "dotenv";

let envLoaded = false;

function tryLoadEnvFile(filepath: string): void {
  if (!fs.existsSync(filepath)) {
    return;
  }
  dotenv.config({ path: filepath, override: false, quiet: true });
}

export function loadServerEnv(): void {
  if (envLoaded) {
    return;
  }

  const uiRoot = process.cwd();
  const projectRoot = path.resolve(uiRoot, "../project");

  tryLoadEnvFile(path.join(uiRoot, ".env.local"));
  tryLoadEnvFile(path.join(uiRoot, ".env"));
  tryLoadEnvFile(path.join(projectRoot, ".env"));

  envLoaded = true;
}

loadServerEnv();

export const UI_ROOT = process.cwd();
export const PIPELINE_CWD =
  process.env.PIPELINE_CWD?.trim() || path.resolve(UI_ROOT, "../project");
export const PIPELINE_DATA_DIR = path.join(PIPELINE_CWD, "data");
export const PIPELINE_RUNS_DIR = path.join(PIPELINE_DATA_DIR, "runs");

export const UI_DATA_DIR = path.join(UI_ROOT, "data");
export const DB_PATH = path.join(UI_DATA_DIR, "runs.db");

export const RETENTION_LIMIT = 30;

export function ensureServerDirectories(): void {
  fs.mkdirSync(UI_DATA_DIR, { recursive: true });
  fs.mkdirSync(PIPELINE_RUNS_DIR, { recursive: true });
}
