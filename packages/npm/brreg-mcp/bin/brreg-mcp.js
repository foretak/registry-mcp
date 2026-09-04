#!/usr/bin/env node
/**
 * brreg-mcp — Node launcher for the Python MCP server.
 *
 * `brreg-mcp` is an alias of `registry-mcp`: the *same* server, published under
 * the name an agent generates when it needs Norwegian company data (KEYWORDS.md
 * §3). This launcher runs the identical Python console script, so the two
 * commands are interchangeable — if they ever diverge, one of them is a bug.
 *
 * The npm package is scoped (`@foretak/brreg-mcp`) because the unscoped npm
 * name `brreg-mcp` was already taken in April 2026 by an unrelated project
 * (`hellosverre/brreg-mcp`). The *PyPI* name `brreg-mcp` is ours and is what
 * SPEC below refers to; the `bin` name stays `brreg-mcp` either way. See
 * SUBMISSIONS.md § Prerequisites.
 *
 * Pure stdio passthrough: the child inherits this process's stdin, stdout and
 * stderr, so the JSON-RPC stream is never buffered, parsed or re-encoded here.
 *
 * Resolution order:
 *   1. `uvx --from brreg-mcp==<version> brreg-mcp`
 *   2. `pipx run --spec brreg-mcp==<version> brreg-mcp`
 *   3. print an install hint on stderr and exit 1
 *
 * Availability is probed with `--version` *before* the real spawn, so a missing
 * launcher never consumes a byte of the caller's stdin.
 *
 * Env:
 *   BRREG_MCP_SPEC  override the Python requirement (a version specifier, a
 *                   path to a wheel, or a VCS URL). Used by CI and for testing
 *                   against a locally built wheel.
 */

"use strict";

const { spawn, spawnSync } = require("node:child_process");

const VERSION = require("../package.json").version;
const SPEC = process.env.BRREG_MCP_SPEC || `brreg-mcp==${VERSION}`;
const ARGS = process.argv.slice(2);

/** True if `cmd --version` runs and exits 0. Never touches stdin. */
function isAvailable(cmd) {
  const probe = spawnSync(cmd, ["--version"], {
    stdio: "ignore",
    shell: process.platform === "win32",
  });
  return !probe.error && probe.status === 0;
}

const INSTALL_HINT = [
  "brreg-mcp: no Python launcher found.",
  "",
  "This package is a thin wrapper around the Python MCP server on PyPI.",
  "It needs Python 3.12+ and one of `uv` or `pipx` on your PATH.",
  "",
  "  Install uv (recommended):",
  "    curl -LsSf https://astral.sh/uv/install.sh | sh      # macOS / Linux",
  "    powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"   # Windows",
  "",
  "  ...or install pipx:",
  "    python3 -m pip install --user pipx",
  "",
  "Then re-run `npx brreg-mcp`, or skip Node entirely:",
  "    uvx brreg-mcp",
  "",
  "Or use the hosted server, which needs nothing installed at all:",
  "    claude mcp add brreg-mcp --transport http https://api.foretak.dev/mcp",
  "",
  "Docs: https://github.com/foretak/registry-mcp",
].join("\n");

/** Candidate launchers, in order of preference. */
const CANDIDATES = [
  { cmd: "uvx", args: ["--from", SPEC, "brreg-mcp", ...ARGS] },
  { cmd: "pipx", args: ["run", "--spec", SPEC, "brreg-mcp", ...ARGS] },
];

const chosen = CANDIDATES.find((c) => isAvailable(c.cmd));

if (!chosen) {
  process.stderr.write(INSTALL_HINT + "\n");
  process.exit(1);
}

const child = spawn(chosen.cmd, chosen.args, {
  stdio: "inherit",
  shell: process.platform === "win32",
});

child.on("error", (err) => {
  process.stderr.write(
    `brreg-mcp: failed to start \`${chosen.cmd}\`: ${err.message}\n\n` +
      INSTALL_HINT +
      "\n"
  );
  process.exit(1);
});

// Forward the signals an MCP client uses to shut a stdio server down.
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => {
    if (!child.killed) child.kill(sig);
  });
}

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code === null ? 1 : code);
  }
});
