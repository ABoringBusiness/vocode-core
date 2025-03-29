FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install FreeSWITCH ESL
RUN git clone https://github.com/signalwire/freeswitch.git /tmp/freeswitch \
    && cd /tmp/freeswitch/libs/esl \
    && make pymod \
    && cd python \
    && python setup.py install \
    && cd / \
    && rm -rf /tmp/freeswitch

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Vocode application
COPY app.py .
COPY .env .

# Expose the port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]