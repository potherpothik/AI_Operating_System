# Build context is the REPO ROOT, same convention as every other
# service's Dockerfile since Phase 19 — this one just has a different
# base image and a 2-stage build (Node to build the real Vite bundle,
# then a lightweight static file server for it).
FROM node:20-slim AS build
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ .
RUN npm run build

FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
EXPOSE 5173
CMD ["serve", "-s", "dist", "-l", "5173"]
