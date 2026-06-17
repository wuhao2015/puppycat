FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time, so they
# must be present as build args before `npm run build` (a runtime env var would
# not affect already-built browser code).
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_API_KEY
ARG NEXT_PUBLIC_MAPBOX_TOKEN
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY
ENV NEXT_PUBLIC_MAPBOX_TOKEN=$NEXT_PUBLIC_MAPBOX_TOKEN

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
