FROM python@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016
RUN python -m pip install --no-cache-dir Pillow==11.3.0
WORKDIR /app
COPY image_service.py /app/
CMD ["python", "image_service.py"]
