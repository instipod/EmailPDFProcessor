FROM python:3.10-bullseye

RUN mkdir /app && mkdir /app/files
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY main.py /app/main.py

RUN apt-get update && apt-get install -y libzbar0
RUN pip3 install -r requirements.txt

ENV BARCODE_VALIDATION_REGEX "^[1-9][0-9]{1,7}$"
ENV BARCODE_TYPES "CODE39;CODE128"
ENV PDF_SAVE_LOCATION "/app/files"
ENV ALLOWED_SENDER_DOMAINS "*"
ENV IMAP_SERVER "imap"
ENV SMTP_SERVER "smtp"
ENV FROM_EMAIL "pdfprocessor@localhost"
ENV FROM_NAME "PDF Processor"
ENV USERNAME "username"
ENV PASSWORD "password"
ENV TZ "America/Chicago"

CMD ["python3", "-u", "/app/main.py"]