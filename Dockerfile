FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false PIP_NO_CACHE_DIR=1
ENV NLTK_DATA=/app/platform_eval/data
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-platform.txt requirements-ml.txt requirements-dashboard.txt requirements-dev.txt requirements-lock.txt ./
# Linux x86 PyPI torch pulls CUDA libraries; explicitly use the CPU wheel index.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 && \
    pip install -c requirements-lock.txt -r requirements-platform.txt -r requirements-ml.txt -r requirements-dashboard.txt -r requirements-dev.txt
RUN useradd --create-home --uid 1000 app && mkdir -p /storage /models /research && chown app:app /storage /models /research
COPY --chown=app:app . /app
USER app
EXPOSE 8000 8501
CMD ["uvicorn", "platform_eval.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
