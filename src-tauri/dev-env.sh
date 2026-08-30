#!/usr/bin/env bash
#
# Optional local-dev environment tuning. Source this (do NOT execute) before a
# local `tauri dev`/`cargo build` to pick up a faster Rust linker on Linux:
#
#     source src-tauri/dev-env.sh
#
# It is also sourced automatically by the `tauri-dev` npm script.
#
# What it does:
#   - On Linux, if the very fast `mold` linker is installed it is used; otherwise
#     LLVM's `lld` is used when available. This only sets RUSTFLAGS for the
#     current shell - it makes dev links dramatically faster (community
#     benchmarks: warm cargo builds ~20s -> ~1-8s).
#   - On macOS / Windows / when neither linker is present it is a no-op, so the
#     system toolchain is used unchanged.
#
# Why this is a sourced env tweak and not a committed .cargo/config.toml flag:
#   the Flatpak release build and macOS CI run without mold/lld, and a forced
#   `-fuse-ld=mold` there would fail the build. Keeping the linker choice
#   detected at dev-shell time means release/CI/Flatpak never see it.

# Don't override an RUSTFLAGS the developer already set, and only act when cargo
# is actually in use (harmless otherwise).
if [ -n "${PHLOX_DEV_ENV_LOADED:-}" ]; then
  return 0 2>/dev/null || true
fi
PHLOX_DEV_ENV_LOADED=1

case "$OSTYPE" in
  linux-gnu*)
    if command -v mold >/dev/null 2>&1 && command -v clang >/dev/null 2>&1; then
      export RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }-C link-arg=-fuse-ld=mold"
      echo "⚡ Fast Rust linker: mold (Linux)"
    elif command -v ld.lld >/dev/null 2>&1 || command -v lld >/dev/null 2>&1; then
      export RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }-C link-arg=-fuse-ld=lld"
      echo "⚡ Fast Rust linker: lld (Linux)"
    else
      echo "ℹ️  mold/lld not found - using the default Rust linker (install mold for faster dev links)"
    fi
    ;;
  darwin*)
    # macOS uses the system ld (and Xcode's linker is already fast for the
    # aarch64-apple-darwin target); nothing to set.
    ;;
  *)
    # Windows / msys: rely on the default MSVC/GNU toolchain.
    ;;
esac
