FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY server.js ./server.js
COPY config.js ./config.js
COPY .env.example ./.env.example

EXPOSE 3000

CMD ["npm", "run", "dev"]
