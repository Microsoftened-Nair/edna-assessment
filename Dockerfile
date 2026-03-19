FROM python:3.10-slim

WORKDIR /app

# Install system dependencies including VSEARCH and BLAST+
RUN apt-get update && apt-get install -y \
    vsearch \
    ncbi-blast+ \
    curl \
    tar \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Taxonkit
RUN curl -L https://github.com/shenwei356/taxonkit/releases/download/v0.14.6/taxonkit_linux_amd64.tar.gz | tar -xz -C /usr/local/bin

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set environment variables
ENV FLASK_APP=edna_api.server:create_app
ENV FLASK_ENV=production
ENV EDNA_DB_DIR=/app/databases
ENV DATABASE_URL=postgresql://postgres:postgres@db:5432/ednadb

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0"]
