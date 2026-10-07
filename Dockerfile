FROM python:3.12-slim

WORKDIR /app

# We need to copy the requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install system dependencies required for WeasyPrint and other libraries.
# Knihovny libnss3..fonts-liberation jsou pro headless Chrome (plotly/kaleido).
# Nazvy balicku jsou pro Debian trixie (64bit time_t -> *t64 varianty).
# fonts-liberation je zamerne: bez pisma Chrome vykresli misto popisku os
# prazdne ctverce.
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libnss3 \
    libnspr4 \
    libatk1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libatspi2.0-0t64 \
    libcups2t64 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2t64 \
    libx11-6 \
    libxcb1 \
    libxext6 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stahni headless Chrome pro kaleido az PO pip install (CLI je z plotly/kaleido)
RUN plotly_get_chrome -y

# Copy the backend code into the container
COPY backend/ /app/

EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]