FROM node:20-alpine as build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
# Label instance pro UI (oranžový pas "Vývojová verze"). Default prod —
# dev image ho přepíše na dev (docker-compose.yml, build.args).
ARG VITE_APP_LABEL=prod
ENV VITE_APP_LABEL=$VITE_APP_LABEL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
