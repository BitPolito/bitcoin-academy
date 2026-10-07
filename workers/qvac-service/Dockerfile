# node:22-slim (glibc), not alpine (musl): the QVAC native runtime and its C++
# addons (rocksdb, llamacpp) are built against glibc and need libatomic/libvulkan.
FROM node:22-slim
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 libvulkan1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
# Clean the npm cache in the same layer: it is ~1.3 GB and never used at runtime.
RUN npm ci --omit=dev && npm cache clean --force
COPY . .
CMD ["node", "src/server.js"]
