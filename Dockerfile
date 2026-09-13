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
ENV DISABLE_OLLAMA=1
ENV GROQ_MAX_RETRIES=1
ENV GROQ_REQUEST_DELAY_SECONDS=12

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

COPY . ./
COPY --from=frontend /app/web/dist ./web/dist

# Hugging Face rejects regular Git binary objects. The deployment workflow
# excludes this database from the Space commit and downloads the public copy.
RUN curl --fail --location \
	https://raw.githubusercontent.com/adam12bT/ai_project0/main/Chinook_Sqlite.sqlite \
	--output Chinook_Sqlite.sqlite

EXPOSE 7860
CMD ["python", "server.py"]