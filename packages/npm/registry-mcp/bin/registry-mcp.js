#!/usr/bin/env node
/**
 * registry-mcp — Node launcher for the Python MCP server.
 *
 * The server itself is Python (PyPI: `registry-mcp`). This package exists so
 * that `npx registry-mcp` works for people whose tooling is Node-first, and so
 * the name is findable on npm as well as PyPI (KEYWORDS.md §2).
 *
 * It is a pure stdio passthrough: the child inherits this process's stdin,
 * stdout and stderr, so the JSON-RPC stream between the MCP client and the
 * server is never buffered, parsed or re-encoded here.
 *
 * Resolution order:
 *   1. `uvx --from registry-mcp==<version> registry-mcp`
 *   2. `pipx run --spec registry-mcp==<version> registry-mcp`
 *   3. print an install hint on stderr and exit 1
 *
 * Availability is probed with `--version` *before* the real spawn, so a missing
 * launcher never consumes a byte of the caller's stdin.
 *
 * Env:
 *   REGISTRY_MCP_SPEC  override the Python requirement (a version specifier, a
 *                      path to a wheel, or a VCS URL). Used by CI and for
 *                      testing against a locally built wheel.
 */

"use strict";

const { spawn, spawnSync } = require("node:child_process");

const VERSION = require("../package.json").version;
const SPEC = process.env.REGISTRY_MCP_SPEC || `registry-mcp==${VERSION}`;
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
  "registry-mcp: no Python launcher found.",
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
  "Then re-run `npx registry-mcp`, or skip Node entirely:",
  "    uvx registry-mcp",
  "",
  "Or use the hosted server, which needs nothing installed at all:",
  "    claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp",
  "",
  "Docs: https://github.com/foretak/registry-mcp",
].join("\n");

/** Candidate launchers, in order of preference. */
const CANDIDATES = [
  { cmd: "uvx", args: ["--from", SPEC, "registry-mcp", ...ARGS] },
  { cmd: "pipx", args: ["run", "--spec", SPEC, "registry-mcp", ...ARGS] },
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
    `registry-mcp: failed to start \`${chosen.cmd}\`: ${err.message}\n\n` +
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
