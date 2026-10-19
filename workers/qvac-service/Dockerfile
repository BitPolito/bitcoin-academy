# node:22-slim (glibc), not alpine (musl): the QVAC native runtime and its C++
# addons (rocksdb, llamacpp) are built against glibc and need libatomic/libvulkan.
FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 libvulkan1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./

# Clean the npm cache and prune unused multimodal QVAC backends + non-Linux prebuilds
# in the same layer so deleted bytes never persist in intermediate image layers.
RUN npm ci --omit=dev \
    && rm -rf \
      node_modules/@qvac/diffusion-cpp \
      node_modules/@qvac/transcription-whispercpp \
      node_modules/@qvac/ocr-onnx \
      node_modules/@qvac/tts-onnx \
      node_modules/@qvac/onnx \
      node_modules/@qvac/translation-nmtcpp \
      node_modules/@qvac/transcription-parakeet \
      node_modules/bare-ffmpeg \
      node_modules/@qvac/llm-llamacpp/prebuilds/android-* \
      node_modules/@qvac/llm-llamacpp/prebuilds/darwin-* \
      node_modules/@qvac/llm-llamacpp/prebuilds/ios-* \
      node_modules/@qvac/llm-llamacpp/prebuilds/win32-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/android-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/darwin-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/ios-* \
      node_modules/@qvac/embed-llamacpp/prebuilds/win32-* \
    && npm cache clean --force

COPY . .

ENV QVAC_WORKER_PATH=/app/src/worker.slim.js

CMD ["node", "src/server.js"]