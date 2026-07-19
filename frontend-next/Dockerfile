FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

EXPOSE 3000

# Serve on 3000 to match docker-compose port mapping and healthcheck.
CMD ["npx", "next", "start", "-p", "3000"]
