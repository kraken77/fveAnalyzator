#!/usr/bin/env node
/** Generuje `public/changelog.json` z historie commitů (běhne při buildu
 * web image, viz frontend-web/Dockerfile). Mimo Docker se spouštět nemusí —
 * commítnutý stub slouží pro host dev (npm run dev).
 *
 * Formát viz frontend-web/src/lib/changelog.ts:
 *   { build: { sha, date, label } | null, entries: [{ sha, date, type, scope, subject }] }
 */
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function git(args) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

// Bez .git (např. ruční build mimo checkout) — nechte stub, jaký je.
const sha = git(["rev-parse", "--short=7", "HEAD"]);
if (!sha) {
  console.log("gen-changelog: .git nedostupné, stub zůstává");
  process.exit(0);
}

const date = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";
const label = process.env.VITE_APP_LABEL || "prod";

// first-parent = historie bez merge duplicit; \x1f jako oddělovač (subject může obsahovat |)
const raw = git([
  "log",
  "--first-parent",
  "--pretty=format:%h%x1f%ad%x1f%s",
  "--date=short",
  "HEAD",
]);

const entries = raw
  .split("\n")
  .filter(Boolean)
  .map((line) => {
    const [s, d, ...rest] = line.split("\x1f");
    const subject = rest.join("\x1f");
    const m = subject.match(/^(\w+)(\(([^)]+)\))?:\s*(.*)$/);
    return {
      sha: s,
      date: d,
      type: m ? m[1].toLowerCase() : "other",
      scope: m ? (m[3] ?? "") : "",
      subject: m ? m[4] : subject,
    };
  });

const file = path.join(root, "public", "changelog.json");
writeFileSync(file, JSON.stringify({ build: { sha, date, label }, entries }, null, 2) + "\n");
console.log(`gen-changelog: ${entries.length} commitů, build ${sha} (${label})`);
