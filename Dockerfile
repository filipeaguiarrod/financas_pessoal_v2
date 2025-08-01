FROM arm64v8/python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/
COPY app.py /app/
COPY src /app/src/
COPY model /app/model/
COPY pages /app/pages/
COPY .streamlit/ ./.streamlit

RUN pip3 install --upgrade pip && pip3 install -r requirements.txt

EXPOSE 8501

CMD streamlit run app.py
