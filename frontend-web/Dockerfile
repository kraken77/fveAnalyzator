# Kontext = KOŘEN repa (compose: context: .) — image potřebuje .git
# (SHA do oranžového pasu) i frontend-web/.
FROM node:20-alpine as build
# git jen pro build info (rev-parse); jinak image git nepoužívá.
RUN apk add --no-cache git
WORKDIR /app

# Nejdřív lockfile + npm ci (layer cache); .git a zdroj až potom,
# protože se mění při každém commitu a nechtíme zbytečně překreslovat npm ci.
COPY frontend-web/package.json frontend-web/package-lock.json ./
RUN npm ci
COPY .git/ .git/
COPY frontend-web/ .

ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
# Label instance pro UI (oranžový pas "Vývojová verze"). Default prod —
# dev image ho přepíše na dev (docker-compose.yml, build.args).
ARG VITE_APP_LABEL=prod
ENV VITE_APP_LABEL=$VITE_APP_LABEL

# Build info do pasu (VITE_* z process env, viz src/lib/appEnv.ts) a
# public/changelog.json z historie commitů (viz scripts/gen-changelog.mjs).
RUN node scripts/gen-changelog.mjs \
 && VITE_BUILD_SHA="$(git -C /app rev-parse --short=7 HEAD 2>/dev/null || echo '?')" \
    VITE_BUILD_DATE="$(date -u '+%Y-%m-%d %H:%M UTC')" \
    npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend-web/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
