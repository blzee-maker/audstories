# AudStories frontend — React + Vite dev server.
#
# Deliberately the dev server rather than a production nginx build: Vite inlines
# VITE_* variables at BUILD time, so a prebuilt image would bake in whatever
# Supabase project it was built against. Running the dev server lets compose pass
# those values at start time, which is what you want for a local evaluation.
#
# For a real deployment, build with `npm run build` and serve frontend/dist from
# any static host, with the VITE_* values set at build time.

FROM node:22-slim

ENV NODE_ENV=development
WORKDIR /app

# package files first so the dependency layer caches independently of source.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host binds 0.0.0.0 so the port is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
