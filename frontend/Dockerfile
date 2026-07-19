# Frontend React/Vite — build estático servido por nginx, que ademas proxya
# /api → backend (mismo origen para el browser, sin CORS).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# build = tsc --noEmit && vite build → genera /app/dist
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
