import io
import smtplib
import re
import os
from datetime import datetime

import pypdfium2 as pdfium
import pytz
from pyzbar import pyzbar
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PyPDF2 import PdfWriter, PdfReader
from imap_tools import MailBox, AND
from email.mime.text import MIMEText
from email.utils import formatdate

GLOBAL_FROM = os.environ.get("FROM_EMAIL")
GLOBAL_DISPLAY_NAME = os.environ.get("FROM_NAME")
GLOBAL_USERNAME = os.environ.get("USERNAME")
GLOBAL_PASSWORD = os.environ.get("PASSWORD")
GLOBAL_IMAP_SERVER = os.environ.get("IMAP_SERVER")
GLOBAL_SMTP_SERVER = os.environ.get("SMTP_SERVER")
GLOBAL_ALLOWED_SENDER_DOMAINS = os.environ.get("ALLOWED_SENDER_DOMAINS")
GLOBAL_PDF_SAVE_LOCATION = os.environ.get("PDF_SAVE_LOCATION")
GLOBAL_BARCODE_VALIDATION_REGEX = os.environ.get("BARCODE_VALIDATION_REGEX")
GLOBAL_BARCODE_TYPES = os.environ.get("BARCODE_TYPES")
GLOBAL_INCLUDE_PAGE_NUMBERS = (os.environ.get("INCLUDE_PAGE_NUMBERS").lower() == "true")
GLOBAL_INCLUDE_RECV_WATERMARK = (os.environ.get("INCLUDE_RECV_WATERMARK").lower() == "true")


def read_barcodes(frame):
    """
    Scans an incoming frame for barcodes and returns their decoded values.
    :param frame: Pillow-compatible image object
    :return: list of decoded barcodes, empty list if none found or valid
    """
    global GLOBAL_BARCODE_VALIDATION_REGEX, GLOBAL_BARCODE_TYPES
    barcodes_detected = pyzbar.decode(frame)
    valid_barcodes = []
    valid_barcode_types = GLOBAL_BARCODE_TYPES.split(";")
    for barcode_detected in barcodes_detected:
        # make sure the barcode type is acceptable, since zbar will read many types
        if barcode_detected.type not in valid_barcode_types:
            continue

        # make sure the barcode data is acceptable
        pattern = re.compile(GLOBAL_BARCODE_VALIDATION_REGEX)
        data = str(barcode_detected.data, 'utf-8')
        if pattern.match(data):
            valid_barcodes.append(barcode_detected)

    return valid_barcodes


def get_pdf_first_frame(pdf_file_bytes):
    """
    Extracts the first page of a PDF to a pillow image for further processing.
    :param pdf_file_bytes: Bytes of a valid PDF file
    :return: Pillow image of the first page
    """
    pdf = pdfium.PdfDocument(pdf_file_bytes)
    page = pdf.get_page(0)
    # scale 300 / 72 = render page at 300 dpi so barcode is readable
    pil_image = page.render_to(
        pdfium.BitmapConv.pil_image,
        scale=300 / 72
    )
    return pil_image


def create_page_number_pdf_page(page, total):
    """
    Creates a PDF page containing a page number footer.  This is used when creating PDF watermarks or overlays.
    :param page: Current page number as an integer
    :param total: Total number of pages in the document as an integer
    :return: PDF page object
    """
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    # set text color to gray
    can.setFillColor(HexColor('#9b9b9b'))
    # page number text overlay is right-aligned
    can.drawRightString(550, 50, f"Page {page} of {total}")
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)
    return new_pdf.pages[0]


def watermark_pdf(pdffile, watermark_texts, name):
    """
    Applies and exports a PDF based on an original PDF plus watermarked overlays.
    :param pdffile: Bytes of a valid PDF file
    :param watermark_texts: list of text lines to apply as a watermark
    :param name: Filename of the exported PDF
    :return: None
    """
    global GLOBAL_PDF_SAVE_LOCATION, GLOBAL_INCLUDE_PAGE_NUMBERS, GLOBAL_INCLUDE_RECV_WATERMARK
    pdf_file_byte_stream = io.BytesIO(pdffile)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    # set text color to gray
    can.setFillColor(HexColor('#9b9b9b'))
    line = 50
    for text in watermark_texts:
        can.drawString(75, line, text)
        # move cursor down 15 each line of text
        line -= 15
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)

    # read the existing PDF
    existing_pdf = PdfReader(pdf_file_byte_stream)
    output = PdfWriter()
    page_count = len(existing_pdf.pages)
    page_number = 1

    # for each page of the existing pdf, add the watermark pdf overlay and the page number overlay
    for existing_page in existing_pdf.pages:
        if GLOBAL_INCLUDE_RECV_WATERMARK:
            existing_page.merge_page(new_pdf.pages[0])
        if GLOBAL_INCLUDE_PAGE_NUMBERS:
            page_number_page = create_page_number_pdf_page(page_number, page_count)
            existing_page.merge_page(page_number_page)
        output.add_page(existing_page)
        page_number += 1

    # finally, write "output" to a real file
    output_stream = open(f"{GLOBAL_PDF_SAVE_LOCATION}/{name}.pdf", "wb")
    output.write(output_stream)
    output_stream.close()


def send_message(to, subject, body, message_id=None):
    """
    Send an outgoing email message.  Attachments are not supported.
    :param to: Destination email address
    :param subject: Subject text
    :param body: Body text
    :param message_id: Optional, should contain Message-ID of original message replying to
    :return: None
    """
    global GLOBAL_FROM, GLOBAL_DISPLAY_NAME, GLOBAL_USERNAME, GLOBAL_PASSWORD, GLOBAL_SMTP_SERVER
    new_msg = MIMEText(body)
    new_msg['Subject'] = subject
    new_msg['From'] = f"\"{GLOBAL_DISPLAY_NAME}\" <{GLOBAL_FROM}>"
    new_msg['To'] = to
    new_msg['Date'] = formatdate(localtime=True)
    new_msg['User-Agent', 'PDF Processor']
    if message_id is not None:
        new_msg['In-Reply-To', message_id]
    s = smtplib.SMTP(GLOBAL_SMTP_SERVER)
    s.login(GLOBAL_USERNAME, GLOBAL_PASSWORD)
    s.sendmail(GLOBAL_FROM, [to], new_msg.as_string())
    s.quit()


def process_message(message):
    """
    Subroutine used for processing incoming messages detected over IMAP.
    :param message: Incoming message object
    :return: None
    """
    global GLOBAL_ALLOWED_SENDER_DOMAINS
    print(f"Processing message: {message.date} from {message.from_}")
    sender = message.from_

    if sender is None or sender == "":
        print("Message from unknown sender declined; no sender address")
        return

    if GLOBAL_ALLOWED_SENDER_DOMAINS != "*":
        allowed_domains = GLOBAL_ALLOWED_SENDER_DOMAINS.split(";")
        sender_domain = sender.split("@")[1]
        if sender_domain not in allowed_domains:
            print(f"Message from {sender} declined; sender domain is not permitted")
            return

    attachment_count = len(message.attachments)

    if attachment_count == 1:
        # read the attachment
        attachment = msg.attachments[0]
        if attachment.content_type == "application/pdf":
            pdf_bytes = attachment.payload
            first_page_image = get_pdf_first_frame(pdf_bytes)
            barcodes = read_barcodes(first_page_image)
            if len(barcodes) == 1:
                now = datetime.now(tz=pytz.timezone(os.environ.get('TZ')))
                date_string = now.strftime("%m/%d/%Y %I:%M:%S %p")
                uploader = sender.split("@")[0]
                watermark_pdf(pdf_bytes,
                              [f"{str(barcodes[0].data, 'utf-8')}", f"{date_string} by {uploader}"],
                              str(barcodes[0].data, 'utf-8'))
            else:
                print(f"Message from {sender} declined; no valid barcode detected")
                send_message(sender, f"[Ingest Failed] Re: {message.subject}",
                             f"The incoming scan '{message.subject}' was declined as it did " +
                             "not contain a single valid barcode.", message.headers['Message-ID'])
        else:
            print(f"Message from {sender} declined; invalid type of attachments: {attachment.content_type}")
            send_message(sender, f"[Ingest Failed] Re: {message.subject}",
                         f"The incoming scan '{message.subject}' was declined as it did " +
                         "not contain a valid type of attachment.", message.headers['Message-ID'])
    else:
        print(f"Message from {sender} declined; invalid number of attachments: {attachment_count}")
        send_message(sender, f"[Ingest Failed] Re: {message.subject}", f"The incoming scan '{message.subject}' was declined as it did " +
                     "not contain the correct number of attachments.", message.headers['Message-ID'])


# start of main code
print("Connecting to IMAP...")

with MailBox(GLOBAL_IMAP_SERVER).login(GLOBAL_USERNAME, GLOBAL_PASSWORD) as mailbox:
    print("Processing existing messages...")
    # process existing messages
    for msg in mailbox.fetch():
        try:
            process_message(msg)
        except Exception as ex:
            print(ex)
            print(f"Message from {msg.from_} failed; exception above occurred")
            send_message(msg.from_, f"[Ingest Failed] Re: {msg.subject}",
                         f"The incoming scan '{msg.subject}' failed to process due to a server error. " +
                         f"Please contact the Helpdesk if this problem continues.",
                         msg.headers['Message-ID'])

        mailbox.delete(msg.uid)

    no_poll_error = True
    while no_poll_error:
        try:
            print("Now using IDLE polling for 60 seconds...")
            # wait for new messages
            with mailbox.idle as idle:
                responses = idle.poll(timeout=60)
            if responses:
                for msg in mailbox.fetch(AND(seen=False)):
                    try:
                        process_message(msg)
                    except Exception as ex:
                        print(ex)
                        print(f"Message from {msg.from_} failed; exception above occurred")
                        send_message(msg.from_, f"[Ingest Failed] Re: {msg.subject}",
                                     f"The incoming scan '{msg.subject}' failed to process due to a server error. " +
                                     f"Please contact the Helpdesk if this problem continues.",
                                     msg.headers['Message-ID'])

                    mailbox.delete(msg.uid)
        except Exception as ex2:
            print(ex2)
            no_poll_error = False
    print("Closing the IMAP connection...")
    mailbox.client.close()
    mailbox.logout()
