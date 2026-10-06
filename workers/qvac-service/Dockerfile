FROM node:22-slim
RUN apt-get update && apt-get install -y libatomic1 libvulkan1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY . .
CMD ["node", "src/server.js"]
