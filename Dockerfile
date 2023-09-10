FROM python:3-slim

# Accept build arguments
ARG DB_SETTINGS

# Set an environment variable using the build argument
ENV DB_SETTINGS=${DB_SETTINGS}

WORKDIR /app

COPY requirements.txt /app/
COPY app.py /app/
COPY src /app/src/
COPY model /app/model/

RUN pip3 install -r requirements.txt

EXPOSE 8501

CMD echo $DB_SETTINGS & streamlit run app.py
