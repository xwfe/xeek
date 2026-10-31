// K070 对照：kdbx.dart 编译到浏览器后能不能真的读写。两种编译方式都试，结果只打印，不进产品路线。
//
//   node drive-dart.mjs     先编译 tests/dart_candidate/bin/web_probe.dart，再在三个引擎里跑
import { execFileSync } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const { chromium, firefox, webkit } = await import("playwright");
const CANDIDATE = join(HERE, "..", "dart_candidate");
const FIXTURES = join(HERE, "..", "fixtures", "kdbx");
const OUT = join(CANDIDATE, "build", "web");
const TYPES = { ".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm" };
const PAGES = {
  "/dart2js.html": '<!doctype html><meta charset="utf-8"><title>dart2js</title><script src="/probe.js"></script>',
  "/dart2wasm.html": `<!doctype html><meta charset="utf-8"><title>dart2wasm</title><script type="module">
    import * as m from "/probe.mjs";
    (await (await m.compileStreaming(fetch("/probe.wasm"))).instantiate()).invokeMain();
  </script>`,
};

const manifest = async (name) => JSON.parse(await readFile(join(FIXTURES, name), "utf8"));
const vault = (await manifest("vault_manifest.json")).samples.find((s) => s.id === "V41-VAULT");
const argon2d = (await manifest("dart_writer_manifest.json")).samples.find((s) => s.file.includes("dk41-rs-vault-argon2d"));
const argon2id = (await manifest("rust_writer_manifest.json")).samples.find((s) => /argon2id/i.test(JSON.stringify(s)));
const CASES = [
  ["AES-KDF", vault.stages.find((s) => s.name === "edit1").file, vault.credentials.password],
  ["Argon2d", argon2d.file, argon2d.password],
  ["Argon2id", argon2id.file, argon2id.password],
];

await mkdir(OUT, { recursive: true });
const environment = { ...process.env, PUB_CACHE: join(CANDIDATE, ".pub-cache") };
for (const [mode, output] of [["js", "probe.js"], ["wasm", "probe.wasm"]]) {
  execFileSync("dart", ["compile", mode, "-o", join(OUT, output), "bin/web_probe.dart"], { cwd: CANDIDATE, env: environment, stdio: "ignore" });
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://localhost");
  try {
    if (PAGES[url.pathname]) {
      response.writeHead(200, { "Content-Type": "text/html" }).end(PAGES[url.pathname]);
    } else if (url.pathname === "/sample") {
      response.end(await readFile(join(FIXTURES, url.searchParams.get("file"))));
    } else {
      const body = await readFile(join(OUT, url.pathname));
      response.writeHead(200, { "Content-Type": TYPES[extname(url.pathname)] ?? "application/octet-stream" }).end(body);
    }
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

for (const [name, type, launch] of [["chrome", chromium, { channel: "chrome" }], ["firefox", firefox, {}], ["webkit", webkit, {}]]) {
  for (const page of Object.keys(PAGES)) {
    const browser = await type.launch({ headless: true, ...launch });
    const tab = await browser.newPage();
    console.log(`${name} ${browser.version()} ${page}`);
    await tab.goto(origin + page);
    await tab.waitForFunction(() => typeof window.keexDartProbe === "function", null, { timeout: 15_000 });
    for (const [label, file, password] of CASES) {
      const result = await tab.evaluate(async ([sample, secret]) => {
        const data = new Uint8Array(await (await fetch(`/sample?file=${encodeURIComponent(sample)}`)).arrayBuffer());
        return window.keexDartProbe(data, secret).then(String);
      }, [file, password]);
      console.log(`  ${label}: ${result.slice(0, 140)}`);
    }
    await browser.close();
  }
}
server.close();
process.exit(0);
