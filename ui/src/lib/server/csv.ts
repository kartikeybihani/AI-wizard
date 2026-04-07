import fs from "node:fs";

import { parse } from "csv-parse/sync";

import type { CsvTableResult } from "@/lib/types";

export function countCsvRows(filepath?: string): number {
  if (!filepath || !fs.existsSync(filepath)) {
    return 0;
  }
  try {
    const text = fs.readFileSync(filepath, "utf-8");
    const records = parse(text, {
      columns: true,
      skip_empty_lines: true,
      relax_quotes: true,
    }) as Record<string, string>[];
    return records.length;
  } catch {
    return 0;
  }
}

export function parseCsv(filepath?: string): CsvTableResult {
  if (!filepath || !fs.existsSync(filepath)) {
    return { columns: [], rows: [] };
  }

  try {
    const text = fs.readFileSync(filepath, "utf-8");
    const rows = parse(text, {
      columns: true,
      skip_empty_lines: true,
      relax_quotes: true,
    }) as Record<string, string>[];

    const columns = rows.length > 0 ? Object.keys(rows[0]) : inferColumnsFromHeader(text);
    return { columns, rows };
  } catch {
    return { columns: [], rows: [] };
  }
}

function inferColumnsFromHeader(text: string): string[] {
  const firstLine = text.split(/\r?\n/, 1)[0]?.trim();
  if (!firstLine) {
    return [];
  }
  return firstLine.split(",").map((item) => item.trim());
}
