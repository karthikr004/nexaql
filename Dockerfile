FROM python:3.12-slim AS backend

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Build frontend
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Final image
FROM python:3.12-slim
WORKDIR /app

COPY --from=backend /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend /usr/local/bin/agentql /usr/local/bin/agentql
COPY --from=backend /app/src /app/src
COPY --from=frontend /app/frontend/dist /app/frontend/dist
COPY ontologies/ ontologies/
COPY agentql.example.yaml agentql.example.yaml

EXPOSE 8080

CMD ["agentql", "serve", "--host", "0.0.0.0", "--port", "8080"]
