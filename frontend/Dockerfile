# Build en DOS ETAPAS (multi-stage):
#   1) "build": Node instala dependencias y compila React a HTML/CSS/JS estáticos.
#   2) imagen final: solo nginx + los archivos compilados. Node, node_modules y el código fuente
#      NO llegan a la imagen final -> más liviana y con mucha menos superficie de ataque.

FROM node:22-alpine AS build
WORKDIR /app
# Primero solo los manifiestos: si el código cambia pero las dependencias no, Docker reutiliza la capa del npm ci
COPY package.json package-lock.json ./
# npm ci instala EXACTAMENTE las versiones de package-lock.json (las mismas que se auditaron con npm audit)
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
