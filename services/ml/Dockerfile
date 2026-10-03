# ML inference service. Large image (torch + onnxruntime); built independently
# of the small Java services so model/inference changes never rebuild those.
FROM python:3.13-slim

# OpenCV / Pillow runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Model weights download from the HF hub on first use; cache them on a volume in
# production so a cold start doesn't re-download.
ENV HF_HOME=/srv/.cache/huggingface \
    WD_TAGGER_MODEL=EVA02_Large \
    WD_TAG_THRESHOLD=0.30

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
