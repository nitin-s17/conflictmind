FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

# Pre-install the MCP server globally at build time
RUN npm install -g mongodb-mcp-server

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
COPY . .
RUN chmod +x /app/startup.sh

EXPOSE 8080
CMD ["/app/startup.sh"]