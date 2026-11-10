FROM python:3.11-slim

WORKDIR /app

# Install dependencies directly (guaranteed to never fail if requirements.txt is missing)
RUN pip install --no-cache-dir aiohttp requests

# Copy all files from current directory
COPY . .

# Expose standard port for Fly.io (matches internal_port in fly.toml)
EXPOSE 7860

CMD ["python", "-u", "paper_copy_trader_bot.py"]
