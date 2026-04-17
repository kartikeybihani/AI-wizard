import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import dotenv from "dotenv";

let envLoaded = false;
const FILE_DIR = path.dirname(fileURLToPath(import.meta.url));
export const UI_ROOT = path.resolve(FILE_DIR, "../../..");

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

  const uiRoot = UI_ROOT;
  const projectRoot = path.resolve(uiRoot, "../project");

  tryLoadEnvFile(path.join(uiRoot, ".env.local"));
  tryLoadEnvFile(path.join(uiRoot, ".env"));
  tryLoadEnvFile(path.join(projectRoot, ".env"));

  envLoaded = true;
}

loadServerEnv();

export const UI_DATA_DIR = path.join(UI_ROOT, "data");
export const SESSION_DIR = path.join(UI_DATA_DIR, "sessions");

export const ELEVENLABS_BASE_URL =
  process.env.ELEVENLABS_BASE_URL?.trim() || "https://api.elevenlabs.io";
export const ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY?.trim() || "";
export const ELEVENLABS_AGENT_ID = process.env.ELEVENLABS_AGENT_ID?.trim() || "";
export const ELEVENLABS_VOICE_ID = process.env.ELEVENLABS_VOICE_ID?.trim() || "";
export const ELEVENLABS_BRANCH_ID = process.env.ELEVENLABS_BRANCH_ID?.trim() || "";

export function ensureServerDirectories(): void {
  fs.mkdirSync(UI_DATA_DIR, { recursive: true });
  fs.mkdirSync(SESSION_DIR, { recursive: true });
}
