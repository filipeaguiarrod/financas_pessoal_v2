FROM python:3-slim

WORKDIR /app

COPY requirements.txt /app/
COPY app.py /app/
COPY src /app/src/
COPY model /app/model/

RUN pip3 install -r requirements.txt

EXPOSE 8501

CMD streamlit run app.py
