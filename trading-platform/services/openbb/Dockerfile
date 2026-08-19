FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    openbb-core==1.6.10 \
    openbb-equity==1.6.2 \
    openbb-yfinance==1.6.3 \
    && openbb-build

EXPOSE 6900

CMD ["uvicorn", "openbb_core.api.rest_api:app", "--host", "0.0.0.0", "--port", "6900"]
