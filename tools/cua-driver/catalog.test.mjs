import { test } from "node:test";
import assert from "node:assert/strict";
import { readCatalog } from "./catalog.mjs";

const allowed = new Set(["list_windows"]);
const fake = `const rl=require('readline').createInterface({input:process.stdin});
rl.on('line',line=>{const m=JSON.parse(line); if(m.id===undefined)return;
const result=m.method==='initialize'?{serverInfo:{name:'fixture'}}:{tools:[{name:'list_windows'},{name:'unsafe'}]};
console.log(JSON.stringify({jsonrpc:'2.0',id:m.id,result}));});`;
test("catalog reads tools once and filters them without actions", async () => {
  assert.deepEqual(await readCatalog(process.execPath, ["-e", fake], allowed), [{ name: "list_windows" }]);
});
test("catalog early exit rejects immediately instead of consuming full timeout", async () => {
  const start = Date.now();
  await assert.rejects(readCatalog(process.execPath, ["-e", "process.exit(7)"], allowed), /exited/);
  assert.ok(Date.now() - start < 5000);
});
test("catalog missing executable rejects without unhandled spawn error", async () => {
  await assert.rejects(readCatalog("missing-cua-driver-fixture-7342", [], allowed), /ENOENT/);
});
test("silent catalog is bounded and is not retried", async () => {
  await assert.rejects(readCatalog(process.execPath, ["-e", "process.stdin.resume()"], allowed,
    { timeoutMs: 100 }), /timed out/);
});
