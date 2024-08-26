import streamlit as st
import imaplib
import pandas as pd
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from openai import OpenAI
from pydantic import BaseModel
import smtplib
import re

# Configuration using secrets
IMAP_SERVER = st.secrets["imap_server"]
EMAIL_ACCOUNT = st.secrets["email_account"]
PASSWORD = st.secrets["email_password"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
client = OpenAI(api_key=OPENAI_API_KEY)


# Functions
def connect_to_email():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, PASSWORD)
    return mail


def fetch_unread_emails(mail, number_of_emails_to_fetch):
    mail.select('inbox')
    status, data = mail.search(None, 'UNSEEN')
    if status != 'OK':
        st.error('Error fetching emails')
        return []

    email_ids = data[0].split()
    emails = []
    for email_id in email_ids[:number_of_emails_to_fetch]:
        status, msg_data = mail.fetch(email_id, '(BODY.PEEK[])')
        if status != 'OK':
            st.warning(f'Error fetching email ID: {email_id}')
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        email_subject, encoding = decode_header(msg['Subject'])[0]
        if isinstance(email_subject, bytes):
            email_subject = email_subject.decode(encoding if encoding else 'utf-8')
        email_from = msg.get('From')
        email_date = parsedate_to_datetime(msg.get('Date')).strftime('%Y-%m-%d %H:%M:%S')
        email_to = msg.get('To')
        email_content = ''
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    email_content += part.get_payload(decode=True).decode()
        else:
            email_content = msg.get_payload(decode=True).decode()
        emails.append({
            'ID': email_id.decode('utf-8'),  # Decode the email ID to string
            'From': email_from,
            'To': email_to,
            'Date': email_date,
            'Subject': email_subject,
            'Content': email_content
        })
    return emails


class EmailSummary(BaseModel):
    importance: int
    response: str
    summary: str


def add_importance_and_response(df):
    system_prompt = (
        "Analyze the email content and provide an importance score between 0 and 5, "
        "with 5 being the most important. Draft a response to the email. "
        "Provide a short and concise one-sentence summary of the email. "
        "Automatically assign a low importance score (1 or 2) to auto-generated emails."
    )
    importance_scores = []
    summaries = []
    responses = []

    progress_bar = st.progress(0)
    total_emails = len(df)

    for i, content in enumerate(df['Content']):
        user_prompt = f"Email: {content}"
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EmailSummary,
        )
        event = completion.choices[0].message.parsed
        importance_scores.append(event.importance)
        summaries.append(event.summary)
        responses.append(event.response)

        # Update progress bar
        progress_bar.progress((i + 1) / total_emails)

    df['Importance Score'] = importance_scores
    df['Summary'] = summaries
    df['Draft Response'] = responses
    return df


def send_email(to_email, subject, body):
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ACCOUNT, PASSWORD)
            message = f"Subject: {subject}\n\n{body}"
            server.sendmail(EMAIL_ACCOUNT, to_email, message)
            return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False


def mark_as_read(email_id):
    mail = connect_to_email()
    mail.select('inbox')
    mail.store(email_id, '+FLAGS', '\\Seen')
    mail.logout()
    print("read")


# Streamlit app
st.set_page_config(page_title="Your Email Buddy", layout="wide")

# Introductory Text
st.title("Your Email Buddy")
st.write("""
This application connects to your email inbox, fetches unread emails, and uses OpenAI to analyze them. 
For each email, the app provides an importance score, a short summary, and a draft response. 
Use this tool to manage your inbox more efficiently and respond to important emails faster.
""")

st.sidebar.header("Settings")
imap_server = st.sidebar.text_input("IMAP Server", IMAP_SERVER)
email_account = st.sidebar.text_input("Email Account", EMAIL_ACCOUNT)
password = st.sidebar.text_input("Password", PASSWORD, type="password")
api_key = st.sidebar.text_input("OpenAI API Key", OPENAI_API_KEY, type="password")
number_of_emails_to_fetch = 5

if st.sidebar.button('Go!') or 'already_started' in st.session_state:
    # Fetch and process emails if not already done
    if 'unread_emails' not in st.session_state:
        with st.spinner("Fetching unread emails..."):
            mail = connect_to_email()
            st.session_state.unread_emails = fetch_unread_emails(mail, number_of_emails_to_fetch)
            mail.logout()
        st.session_state.already_started = True

    if st.session_state.unread_emails:
        df = pd.DataFrame(st.session_state.unread_emails)
        with st.expander("Unread Emails"):
            st.dataframe(df)
        if 'processed_emails' not in st.session_state:
            with st.spinner("Analyzing emails..."):
                st.session_state.processed_emails = add_importance_and_response(df)

        st.write("### Processed Emails")

        df = st.session_state.processed_emails.sort_values(by='Importance Score', ascending=False)

        st.write("""
        **Importance Score Key:**
        - 🔥: Very High Importance
        - 🔴: High Importance
        - 🟠: Medium Importance
        - 🟡: Low Importance
        - 🟢: Very Low Importance
        """)

        for idx, row in df.iterrows():
            importance_emoji = "🔥" if row['Importance Score'] == 5 else \
                "🔴" if row['Importance Score'] == 4 else \
                    "🟠" if row['Importance Score'] == 3 else \
                        "🟡" if row['Importance Score'] == 2 else \
                            "🟢"

            expander_key = f"expander_{idx}"
            expander_title = f"{importance_emoji} {row['Summary']}"

            with st.expander(expander_title):
                st.write(f"**From:** {row['From']}")
                st.write(f"**Date:** {row['Date']}")
                st.write(f"**Subject:** {row['Subject']}")
                st.write(f"**Original Content:** {row['Content']}")

                response_key = f"response_{idx}"
                draft_response = st.text_area("Edit draft response:", value=row['Draft Response'], key=response_key)

                if st.button(f"Send ✉️", key=f"send_{idx}"):
                    with st.spinner(f"Sending reply..."):
                        success = send_email(row['From'], row['Subject'], draft_response)
                    if success:
                        with st.spinner(f"Marking email from {row['From']} as read..."):
                            mark_as_read(row['ID'])
                        st.success(f"Response sent to {row['From']}")

                        # Remove the email from the processed emails DataFrame
                        st.session_state.processed_emails = st.session_state.processed_emails.drop(idx)
                        del st.session_state[f"response_{idx}"]  # Clean up the response text area state
                        st.rerun()  # Rerun the app to update the interface

    else:
        st.info("No unread emails found.")
