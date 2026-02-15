FROM python:3.13.5-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY app.py ./
COPY logic.py ./

# Create empty assets & tests directories to match copy pattern if needed, or just skip
# We will copy the assets folder if it exists
COPY assets ./assets
# We will copy packages too if needed
COPY packages.txt ./

RUN pip3 install -r requirements.txt

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
