FROM python:3.10-bullseye

RUN mkdir /app && mkdir /app/files
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y libzbar0
RUN pip3 install -r requirements.txt

COPY main.py /app/main.py

ENV BARCODE_VALIDATION_REGEX "^[1-9][0-9]{1,7}$"
ENV BARCODE_TYPES "CODE39;CODE128"
ENV PDF_SAVE_LOCATION "/app/files"
ENV ALLOWED_SENDER_DOMAINS "*"
ENV IMAP_SERVER "imap"
ENV IMAP_PORT 143
ENV IMAP_SECURE "false"
ENV SMTP_SERVER "smtp"
ENV SMTP_PORT 25
ENV SMTP_SECURE "false"
ENV FROM_EMAIL "pdfprocessor@localhost"
ENV FROM_NAME "PDF Processor"
ENV USERNAME "username"
ENV PASSWORD "password"
ENV INCLUDE_RECV_WATERMARK "true"
ENV INCLUDE_PAGE_NUMBERS "true"
ENV SEND_SUCCESS_REPLY "true"
ENV TZ "America/Chicago"
ENV NAME_PREFIX ""
ENV PROCESSING_COMMAND "exit 0"

CMD ["python3", "-u", "/app/main.py"]