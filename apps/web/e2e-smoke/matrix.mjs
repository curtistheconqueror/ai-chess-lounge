// usage: node e2e-smoke/matrix.mjs smoke-out/matrix1.json [--detail ID]
import fs from "node:fs";
const d = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const detail = process.argv.includes("--detail") ? process.argv[process.argv.indexOf("--detail") + 1] : null;
const rows = {}; const projects = new Set();
function* walk(s) { for (const x of s.suites ?? []) yield* walk(x); for (const sp of s.specs ?? []) for (const t of sp.tests) yield [sp, t]; }
for (const [sp, t] of walk(d)) {
  const id = (sp.title.match(/\[(S\d+[^\]]*)\]/) ?? [, sp.title])[1];
  const r = t.results[t.results.length - 1];
  const st = r.status === "passed" ? "." : r.status === "skipped" ? "-" : "F";
  (rows[id] ??= {})[t.projectName] = st; projects.add(t.projectName);
  if (detail && id === detail) {
    console.log(t.projectName, r.status, (r.errors ?? []).map(e => e.message.split("\n")[0].replace(/\u001b\[[0-9;]*m/g, "").slice(0, 220)).join(" ; "));
    for (const a of t.annotations ?? []) if (a.type !== "skip") console.log("    ", a.type, (a.description ?? "").slice(0, 300));
  }
}
if (!detail) {
  const ps = [...projects];
  console.log("ID".padEnd(14) + ps.map((p, i) => String(i).padStart(3)).join(""));
  ps.forEach((p, i) => console.log(`  ${i}=${p}`));
  for (const id of Object.keys(rows).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })))
    console.log(id.padEnd(14) + ps.map(p => (rows[id][p] ?? " ").padStart(3)).join(""));
}
