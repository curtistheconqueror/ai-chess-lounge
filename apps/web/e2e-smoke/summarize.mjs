// usage: node e2e-smoke/summarize.mjs results.json
import fs from "node:fs";
const d = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
function* walk(s) {
  for (const x of s.suites ?? []) yield* walk(x);
  for (const sp of s.specs ?? []) for (const t of sp.tests) {
    const r = t.results[t.results.length - 1];
    yield [t.projectName, sp.title.slice(0, 60), r.status, (r.errors ?? []).map(e => e.message.split("\n")[0].replace(/\u001b\[[0-9;]*m/g, "").slice(0, 200)), (t.annotations ?? []).map(a => `${a.type}: ${(a.description ?? "").slice(0, 400)}`)];
  }
}
const showNotes = process.argv.includes("--notes");
for (const [p, t, s, e, a] of walk(d)) {
  console.log(`${s.toUpperCase().padEnd(8)} ${p} | ${t}`);
  for (const x of e) console.log("     ERR ", x);
  if (showNotes) for (const x of a) console.log("     NOTE", x);
}
