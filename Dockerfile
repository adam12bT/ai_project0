FROM node:20-alpine AS frontend

WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

COPY . ./
COPY --from=frontend /app/web/dist ./web/dist

EXPOSE 7860
CMD ["python", "server.py"]