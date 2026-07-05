FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN for i in 1 2 3; do \
      rm -rf node_modules && \
      npm install --no-audit --no-fund && \
      test -x node_modules/.bin/next && break; \
      test "$i" = "3" && exit 1; \
      sleep 2; \
    done

COPY . .

ARG NEXT_PUBLIC_MAPBOX_TOKEN
ARG API_INTERNAL_BASE_URL
ENV NEXT_PUBLIC_MAPBOX_TOKEN=$NEXT_PUBLIC_MAPBOX_TOKEN
ENV API_INTERNAL_BASE_URL=$API_INTERNAL_BASE_URL

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
