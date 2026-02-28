FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

COPY pyproject.toml /app/
COPY uv.lock /app/
COPY app.py /app/
COPY src /app/src/
COPY model /app/model/
COPY pages /app/pages/
COPY .streamlit/ ./.streamlit

RUN uv sync --frozen

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app.py"]