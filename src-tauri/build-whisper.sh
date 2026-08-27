#!/usr/bin/env bash
# Build the whisper.cpp OpenAI-compatible ASR server used by the desktop app.
# The same binary can load the three bundled large-v3-turbo GGML variants.
#
# Use --debug to copy the binary to target/debug for `tauri dev`.

set -euo pipefail

DEBUG_MODE=false
for arg in "$@"; do
  case "$arg" in
    --debug) DEBUG_MODE=true ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHISPER_DIR="$SCRIPT_DIR/whisper.cpp"
WHISPER_REF="${WHISPER_CPP_REF:-978113305b2ead22249b881deafa131dc8884911}"

if [ ! -d "$WHISPER_DIR" ]; then
  echo "Cloning whisper.cpp ($WHISPER_REF)..."
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$WHISPER_DIR"
  git -C "$WHISPER_DIR" fetch --depth 1 origin "$WHISPER_REF"
  git -C "$WHISPER_DIR" checkout --detach FETCH_HEAD
elif [ ! -f "$WHISPER_DIR/CMakeLists.txt" ]; then
  echo "whisper.cpp checkout is incomplete: $WHISPER_DIR"
  exit 1
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
  JOBS=$(sysctl -n hw.logicalcpu)
  BACKEND_FLAGS=(-DGGML_METAL=ON -DGGML_NATIVE=ON)
  BUILD_CONFIG_FLAGS=()
  SERVER_NAME="phlox-whisper-server"
  BACKEND="Metal"
elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "win32"* ]]; then
  JOBS=${NUMBER_OF_PROCESSORS:-4}
  BACKEND_FLAGS=(-DGGML_NATIVE=OFF)
  BUILD_CONFIG_FLAGS=(--config Release)
  SERVER_NAME="phlox-whisper-server.exe"
  BACKEND="CPU"
else
  JOBS=$(nproc)
  BACKEND_FLAGS=(-DGGML_NATIVE=OFF)
  BUILD_CONFIG_FLAGS=()
  SERVER_NAME="phlox-whisper-server"
  BACKEND="CPU"
fi

rm -rf "$WHISPER_DIR/build"
cmake -S "$WHISPER_DIR" -B "$WHISPER_DIR/build" \
  -DCMAKE_BUILD_TYPE=Release \
  "${BACKEND_FLAGS[@]}" \
  -DBUILD_SHARED_LIBS=OFF \
  -DWHISPER_BUILD_SERVER=ON \
  -DWHISPER_BUILD_EXAMPLES=ON \
  -DWHISPER_BUILD_TESTS=OFF \
  -DWHISPER_BUILD_BENCHMARKS=OFF \
  -DWHISPER_USE_COREML=OFF

cmake --build "$WHISPER_DIR/build" --target whisper-server -j"$JOBS" "${BUILD_CONFIG_FLAGS[@]}"

SERVER_BIN=""
for candidate in \
  "$WHISPER_DIR/build/bin/whisper-server" \
  "$WHISPER_DIR/build/bin/whisper-server.exe" \
  "$WHISPER_DIR/build/bin/Release/whisper-server.exe"; do
  if [ -f "$candidate" ]; then
    SERVER_BIN="$candidate"
    break
  fi
done
if [ -z "$SERVER_BIN" ]; then
  echo "whisper-server was not produced"
  find "$WHISPER_DIR/build" -type f -name 'whisper-server*' -print
  exit 1
fi

cp "$SERVER_BIN" "$SCRIPT_DIR/$SERVER_NAME"
chmod +x "$SCRIPT_DIR/$SERVER_NAME"

if command -v patchelf >/dev/null 2>&1 && [[ "$OSTYPE" != "darwin"* && "$OSTYPE" != "msys"* && "$OSTYPE" != "win32"* ]]; then
  patchelf --remove-rpath "$SCRIPT_DIR/$SERVER_NAME" 2>/dev/null || true
fi

if [ "$DEBUG_MODE" = true ]; then
  mkdir -p "$SCRIPT_DIR/target/debug"
  cp "$SCRIPT_DIR/$SERVER_NAME" "$SCRIPT_DIR/target/debug/$SERVER_NAME"
  chmod +x "$SCRIPT_DIR/target/debug/$SERVER_NAME"
fi

echo "whisper.cpp ASR server built with $BACKEND support: $SCRIPT_DIR/$SERVER_NAME"
