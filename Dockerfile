FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

# Copia só as deps primeiro — camada cacheada enquanto pyproject/uv.lock não mudam
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copia o código — qualquer mudança aqui não invalida o cache do uv sync
COPY app.py ./
COPY src ./src/
COPY model ./model/
COPY pages ./pages/
COPY .streamlit ./.streamlit

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app.py"]
