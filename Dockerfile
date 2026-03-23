FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py *.html ./

# Create .env file with defaults if it doesn't exist
RUN if [ ! -f .env ]; then echo "ADMIN_USERNAME=admin\nADMIN_PASSWORD=admin123" > .env; fi

EXPOSE 8090

CMD ["python", "app.py"]
