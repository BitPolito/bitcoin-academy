# node:22-slim (glibc), not alpine (musl): the QVAC native runtime and its C++
# addons (rocksdb, llamacpp) are built against glibc and need libatomic/libvulkan.
FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 libvulkan1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./

# Clean the npm cache and prune unused multimodal QVAC backends + non-Linux prebuilds
# in the same layer so deleted bytes never persist in intermediate image layers.
# The trailing * also removes each backend's per-platform package
# (e.g. @qvac/diffusion-cpp-linux-x64). turbovec-ggml is kept: the
# embedding plugin uses it as its vector index.
RUN npm ci --omit=dev \
    && rm -rf \
      node_modules/@qvac/asr-ggml* \
      node_modules/@qvac/audiogen-ggml* \
      node_modules/@qvac/bci-whispercpp* \
      node_modules/@qvac/classification-ggml* \
      node_modules/@qvac/decoder-audio* \
      node_modules/@qvac/diffusion-cpp* \
      node_modules/@qvac/ocr-ggml* \
      node_modules/@qvac/translation-nmtcpp* \
      node_modules/@qvac/tts-ggml* \
      node_modules/@qvac/vla-ggml* \
      node_modules/bare-ffmpeg \
      node_modules/@qvac/llm-llamacpp/prebuilds/android-* \
      node_modules/@qvac/llm-llamacpp/prebuilds/darwin-* \
      node_modules/@qvac/llm-llamacpp/prebuilds/ios-* \
      node_modules/@qvac/llm-llamacpp/prebuilds/win32-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/android-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/darwin-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/ios-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/win32-* \
      node_modules/@qvac/turbovec-ggml/prebuilds/android-* \
      node_modules/@qvac/turbovec-ggml/prebuilds/darwin-* \
      node_modules/@qvac/turbovec-ggml/prebuilds/ios-* \
      node_modules/@qvac/turbovec-ggml/prebuilds/win32-* \
    && npm cache clean --force

COPY . .

ENV QVAC_WORKER_PATH=/app/src/worker.slim.js

CMD ["node", "src/server.js"]
