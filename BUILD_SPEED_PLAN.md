# Phlox — Faster, Lighter Builds: Dev & Production Plan

Date: 2026-08-30 · Branch: `arena/01a052f4-phlox-persian`

A focused, evidence-based plan to cut build/iteration time and shrink shipped
weight, compiled from the newest reliable sources (Vite/Rolldown, Tauri,
Nuitka, ggml/llama.cpp docs, VoidZero/Oxlint, Astral/uv, and Rust build-tooling
write-ups) plus GitHub/Reddit discussion. This builds on the optimizations
**already applied** on this branch (see
[`BUILD_OPTIMIZATION_REPORT.md`](./BUILD_OPTIMIZATION_REPORT.md)).

> Ground rules honored: no dependency upgrades, no behavior change, codesign /
> CSP / notarization untouched, macOS + Linux, CI stays green,
> `build-all.sh --skip-cpp` preserved.

---

## 0. Where time actually goes today

| Stage | Dev (`tauri dev`) | Release (`build-all.sh` + `tauri build`) | Dominant cost |
|---|---|---|---|
| Frontend (Vite 8 / Rolldown) | ~0.2–2 s start; HMR | **~2 s** ✅ already fast | already on Rolldown |
| Rust shell (cargo) | incremental, relinks on change | compiles all deps fresh in **CI** (no `target/` cache) | linker + cold dependency build |
| C++ sidecars (llama/whisper/parakeet) | skipped via `--skip-cpp` normally | 3–9 min, now incremental ✅ | C compilation |
| Python server (Nuitka) | uses `uvicorn` (not Nuitka) in dev ✅ | ~10 min, now ccache-backed ✅ | Python→C compile |
| npm install | ~11–45 s | same | network + extraction |
| Docker | bind mounts, fast | layer + download | downloads |

The frontend is **already** on Vite 8 (Rolldown) — the single biggest modern
win — and the native incremental/ccache work from the previous pass removes the
worst repeat-build costs. The remaining high-value targets are: **Rust/CI
caching + linker**, the **Ninja** generator for C++, the **Rust dev profile**,
and a **fast-lint pre-pass**.

---

## 1. Already done on this branch (recap)

- Incremental CMake build dirs (no more unconditional `rm -rf build`) +
  `ccache`/`sccache` launcher for llama/whisper/parakeet/Nuitka, via new
  `src-tauri/build-common.sh`.
- Persistent local `NUITKA_CACHE_DIR`; `build-server.sh --clean` escape hatch;
  CI cache paths untouched.
- BuildKit cache mounts (npm/apt/uv) + `UV_LINK_MODE=copy` + layer split in
  `Dockerfile` / `Dockerfile.dev`.
- Dev no longer wipes `node_modules/.vite`; Vite `vendor-react` chunk split.

---

## 2. NEW — Quick wins (safe, < 30 min each)

### Q1. Cache the Rust build in CI with `swatinem/rust-cache`  ⭐ highest CI ROI
**Problem:** `.github/workflows/build.yml` caches Nuitka/ccache but **never
caches `src-tauri/target/`** — every release run recompiles Tauri + webkit/objc2
+ serde + all crates from scratch.
**Change:** add one step after "Install Rust":
```yaml
      - name: Rust cache
        uses: Swatinem/rust-cache@v2
        with:
          workspaces: "./src-tauri -> target"
```
- **Impact:** High on CI (minutes saved on every run; near-total cache hit when
  only frontend/server changed).
- **Risk:** Safe (read/write cache only). **Effort:** Trivial.
- **Verify:** two CI runs on the same PR — second run's `cargo build` is much
  faster; cache restored log line appears. **Rollback:** delete the step.
- Source: Tauri official CI guide ([v2.tauri.app/distribute/pipelines/github](https://v2.tauri.app/distribute/pipelines/github/)), [Tauri cross-platform guide](https://v1.tauri.app/v1/guides/building/cross-platform/).

### Q2. Use the Ninja generator for the C++ sidecars
**Problem:** scripts let CMake pick Unix Makefiles; ggml explicitly recommends
**Ninja** (parallel + no re-check overhead) and `ccache` for repeated builds.
**Change (in `build-common.sh` + the 3 C++ scripts):**
- detect `ninja`/`ninja-build`; if present add `-G Ninja` (and
  `-DCMAKE_BUILD_PARALLEL_LEVEL=<jobs>`), else fall back to Makefiles.
- explicitly pass `-DGGML_CCACHE=ON` (default ON, but make it deterministic);
  keep the `CMAKE_*_COMPILER_LAUNCHER` flags.
- include the generator in the build-signature (already exists) so switching
  generators triggers a one-time clean rebuild automatically.
- **Requires:** `brew install ninja` (mac) / `apt install ninja-build` (Linux);
  CI: add `ninja` to the `brew install` line.
- **Impact:** Medium (faster C++ configure/link; cleaner incremental). **Risk:**
  Safe (auto-fallback when Ninja absent). **Effort:** Easy.
- **Verify:** `bash src-tauri/build-whisper.sh` logs `using Ninja`; rebuild is a
  no-op in seconds. **Rollback:** uninstall ninja / revert.
- Source: llama.cpp build docs ([building from source](https://mintlify.wiki/ggml-org/llama.cpp/development/building), [docs/build.md](https://github.com/osllmai/llama.cpp/blob/main/docs/build.md)); ggml `CMakeLists.txt` ships `GGML_CCACHE` ([ggml CMakeLists](https://huggingface.co/spaces/Steven10429/apply_lora_and_quantize/blob/main/llama.cpp/ggml/CMakeLists.txt)).

### Q3. Add a Rust fast-linker config (dev-focused, macOS-safe)
**Problem:** a large share of Rust edit–build time is the linker; there is no
`.cargo/config.toml`.
**Change:** create `src-tauri/.cargo/config.toml`, gated per target so macOS
keeps its default (`ld-prime`/`zld` path) and Linux uses `mold`/`lld` only if
installed:
```toml
# Linux: use mold if present, else lld; macOS uses the system linker.
[target.x86_64-unknown-linux-gnu]
linker = "clang"
rustflags = ["-C", "link-arg=-fuse-ld=mold"]
```
(Detect availability in `build-all.sh`/docs; or document
`RUSTFLAGS="-C link-arg=-fuse-ld=lld"`.) On macOS Tauri already targets
`aarch64-apple-darwin`, where the default linker is correct — **do not** force
mold there.
- **Impact:** Medium on Linux dev/CI link time (community reports warm builds
  20 s → 1.2–8 s). **Risk:** Moderate (Linux-only, needs the linker installed;
  guard so a missing linker doesn't break the build). **Effort:** Easy.
- **Verify:** `cargo build` twice in `src-tauri`; second link is faster.
  **Rollback:** delete the file.
- Sources: David Lattimore's Rust edit-build-run benchmarks
  ([20 s→1.2 s](https://davidlattimore.github.io/posts/2024/02/04/speeding-up-the-rust-edit-build-run-cycle.html));
  Tauri maintainer recommends lld
  ([tauri#1733](https://github.com/tauri-apps/tauri/discussions/1733));
  r/rust Tauri thread uses mold
  ([reddit](https://www.reddit.com/r/rust/comments/1kq78dt/)).

### Q4. Tune the Rust **dev** profile (faster `tauri dev` iterations)
**Problem:** default `dev` profile builds all deps with full debuginfo, slowing
links.
**Change:** in `src-tauri/Cargo.toml`:
```toml
[profile.dev]
incremental = true
[profile.dev.package."*"]
opt-level = 1
debug = false
```
- **Impact:** Medium for `tauri dev` rebuilds (~15 s→~10 s reported in the
  community); first build after the change recompiles deps once.
- **Risk:** Safe (dev only; doesn't touch release). **Effort:** Trivial.
- **Verify:** touch a `.rs` file during `tauri dev`, time recompile.
  **Rollback:** remove the profile.
- Sources: [yuexunj.com "Make Your Tauri Dev Faster"](https://yuexunj.com/how-to-make-your-tauri-dev-faster/), [Tauri app-size docs](https://v2.tauri.app/concept/size/).

### Q5. Add Oxlint as a fast first-pass linter (keep ESLint)
**Problem:** `npm run lint` (ESLint) takes ~22 s here; it's part of the
feedback loop.
**Change (additive, no removal):**
- `npm i -D oxlint`; add `"lint:fast": "oxlint"` and make `lint` run
  `oxlint && eslint` (or add `eslint-plugin-oxlint` to turn off rules Oxlint
  already covers). ESLint stays the source of truth for the few plugin/
  type-aware rules Oxlint doesn't have (this repo uses react-hooks +
  unused-imports).
- **Impact:** Low–Medium dev/CI feedback (lint drops to ~1 s for the Oxlint
  pass; ESLint still runs for coverage). **Risk:** Safe (additive; never
  *replaces* ESLint). **Effort:** Easy.
- **Verify:** `npm run lint:fast` ; `npm run lint` still green. **Rollback:**
  remove the dep/script.
- Sources: [Announcing Oxlint 1.0 (VoidZero)](https://voidzero.dev/posts/announcing-oxlint-1-stable) (50–100× faster, used by Shopify/Airbnb/Mercedes); [PkgPulse Oxlint vs ESLint 2026](https://www.pkgpulse.com/blog/oxlint-vs-eslint-rust-linting-performance-2026) (recommends hybrid `oxlint && eslint`).

---

## 3. Medium-term (needs testing before a release)

### M1. Nuitka: clean venv + anti-bloat + no dev-server LTO
- Build the standalone from a **minimal venv** that contains only the runtime
  extras (`--extra docker`/`rag`/`asr`, not the `dev` group with pytest/ruff/ty/
  nuitka tooling). A "dirty" venv makes Nuitka follow and compile extra modules,
  inflating both time and the `server_dist/` bundle.
- Review `--include-package`/`--nofollow-import-to` to drop anything not reached
  at runtime (Nuitka anti-bloat plugin). Leave `--lto` **off** for build speed
  unless you want the runtime/size win and accept the longer compile (LTO/PGO
  increase compile time substantially).
- **Impact:** Medium (faster Nuitka + smaller `server_dist`). **Risk:** Moderate
  (over-pruning breaks runtime imports → test the packaged app). **Effort:**
  Moderate. **Verify:** launch the packaged app, exercise PDF/RAG/ASR paths.
- Sources: Nuitka manual/tips ([nuitka.net](https://nuitka.net/user-documentation/tips.html)); r/Python compiler thread (clean venv, LTO/PGO trade-offs) ([reddit](https://www.reddit.com/r/Python/comments/1ncy8av/)).

### M2. sccache for Rust in CI (shared, content-addressed)
- Beyond `swatinem/rust-cache` (Q1), optionally set `RUSTC_WRAPPER=sccache` with
  `mozilla-actions/sccache-action` + `SCCACHE_GHA_ENABLED=true`. Starts building
  immediately and fetches only needed artifacts (avoids the coarse whole-`target`
  blob restore). Note: crate-level benefits for a small Tauri shell are modest
  versus Q1; do Q1 first.
- **Impact:** Medium (CI). **Risk:** Moderate. **Effort:** Easy.
- Source: [Depot: Fast Rust Builds with sccache and GHA](https://depot.dev/blog/sccache-in-github-actions).

### M3. Optional release profile for **smaller** app binaries (weight, not speed)
- If shrinking the DMG/.app matters, add a size-tuned release profile:
  ```toml
  [profile.release]
  opt-level = "s"   # or "z" for smallest
  lto = true
  codegen-units = 1
  strip = true
  panic = "abort"
  ```
  This **reduces binary size 30–40%** but makes release compiles *slower* — so
  gate it behind a separate choice/flag, don't force it for iteration.
- **Impact:** Medium weight / negative build-time. **Risk:** Moderate (test
  signing/notarization with stripped binaries). **Effort:** Easy.
- Source: [Tauri app-size docs](https://v2.tauri.app/concept/size/).

### M4. Frontend: keep lazy boundaries intact; try Full Bundle Mode in dev
- The Rolldown split is already tuned (React isolated; pdfjs/pdf-lib/Chakra stay
  lazy — verified). Do **not** widen vendor chunks (measured to pull lazy code
  eager).
- Experimental: Vite 8 **Full Bundle Mode** for dev reports ~3× faster dev-server
  start, 40% faster full reloads, 10× fewer requests on large apps. Test in a
  spike; it's experimental and can change HMR behavior.
- **Impact:** Medium dev startup on large codebases (this app is small → low).
  **Risk:** Moderate (experimental). **Effort:** Easy to spike.
- Source: [Vite 8 announcement](https://vite.dev/blog/announcing-vite8).

---

## 4. Architectural (only with explicit approval)

### A1. Pre-built sidecar binaries (largest native time saver)
Publish/download static `llama-server`/`whisper-server`/`parakeet-server` for the
pinned SHAs per OS/arch (with Metal/static/rpath + notarization handled), and
have `build-all.sh` download when a matching artifact exists, falling back to
compiling. Removes ~5–9 min of C++ from most builds. Effort is in the release
pipeline + integrity verification. Risk: Moderate–Risky (must match the current
hand-built binary behavior exactly).

### A2. npm → pnpm
pnpm is the reliable 2026 default for speed/disk: ~2–4× faster installs,
content-addressable store (50–70% disk), strict phantom-dep blocking,
`--frozen-lockfile`, and it supports the same supply-chain posture the repo's
`.npmrc` already encodes (`ignore-scripts`, min-release-age). Migration = new
lockfile + `packageManager` field + CI `setup-node` cache (`pnpm`) + Dockerfile
`corepack`/`pnpm fetch`. Bun is fastest cold but changes the runtime/lockfile
and has edge-case risk — pnpm is the conservative pick.
- **Impact:** Medium (install ~45 s→~8–30 s; big disk/CI-layer wins). **Risk:**
  Moderate (lockfile/CI/Docker churn; validate native-ish deps). **Effort:**
  Moderate.
- Sources: [Syncfusion pnpm vs npm vs yarn 2026](https://www.syncfusion.com/blogs/post/pnpm-vs-npm-vs-yarn), [dev.to 2026 guide](https://dev.to/_d7eb1c1703182e3ce1782/npm-vs-pnpm-vs-yarn-which-package-manager-should-you-use-in-2026-3o3o), [hirenodejs 2026](https://www.hirenodejs.com/blog/nodejs-package-managers-2026), [OpenReplay](https://blog.openreplay.com/switch-npm-pnpm/).

### A3. Docker: multi-stage uv builder / distroless
Copy a pre-built `.venv` from a builder stage (drop `uv` from the runtime
image, smaller attack surface) — or distroless, *if* tesseract/tzdata/CA-certs
and uvicorn signal handling are re-provided. Out of scope for a no-behavior-change
pass. Source: [hynek.me Production-ready Python containers with uv](https://hynek.me/articles/docker-uv/).

---

## 5. Recommended order

1. **Q1** Rust CI cache (`swatinem/rust-cache`) — biggest CI win, trivial.
2. **Q4** Rust dev profile + **Q3** Linux fast linker — faster `tauri dev`.
3. **Q2** Ninja + explicit `GGML_CCACHE` — faster native builds.
4. **Q5** Oxlint fast pass — faster feedback.
5. Then evaluate **M1** (Nuitka lean venv) and, if weight matters, **M3**.
6. Schedule **A1** (prebuilt sidecars) and **A2** (pnpm) as dedicated efforts.

Every item above is additive and independently revertible; the first five are
the safe, high-return set and can be implemented + verified with
`npm run typecheck`, `npm test -- --run`, `npm run lint`, and
`bash -n src-tauri/build-*.sh` without a full native toolchain.
