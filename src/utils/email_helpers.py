import email
import imaplib
import smtplib
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

import streamlit as st


def connect_to_email(imap_server, email_account, password):
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(email_account, password)
    return mail


def fetch_unread_emails(mail, number_of_emails_to_fetch):
    mail.select("inbox")
    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        st.error("Error fetching emails")
        return []

    email_ids = data[0].split()
    emails = []
    for email_id in email_ids[:number_of_emails_to_fetch]:
        status, msg_data = mail.fetch(email_id, "(BODY.PEEK[])")
        if status != "OK":
            st.warning(f"Error fetching email ID: {email_id}")
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        email_subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(email_subject, bytes):
            email_subject = email_subject.decode(encoding if encoding else "utf-8")

        email_from_full = msg.get("From")
        email_from = parseaddr(email_from_full)[1]  # Extract just the email address

        email_date = parsedate_to_datetime(msg.get("Date")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        email_content = get_email_content(msg)

        emails.append(
            {
                "ID": email_id.decode("utf-8"),
                "From": email_from,
                "To": msg.get("To"),
                "Date": email_date,
                "Subject": email_subject,
                "Content": email_content,
            }
        )
    return emails


def get_email_content(msg):
    if msg.is_multipart():
        content = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                content.append(part.get_payload(decode=True).decode())
        return "".join(content)
    return msg.get_payload(decode=True).decode()


def send_email(to_email, subject, body, email_account, password):
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_account, password)
            message = f"Subject: {subject}\n\n{body}"
            server.sendmail(email_account, to_email, message)
            return True
    except smtplib.SMTPException as error:
        st.error(f"Failed to send email: {error}")
        return False


def mark_as_read(email_id, imap_server, email_account, password):
    mail = connect_to_email(imap_server, email_account, password)
    mail.select("inbox")
    mail.store(email_id, "+FLAGS", "\\Seen")
    mail.logout()
