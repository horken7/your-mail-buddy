import json
import time

import streamlit as st
import imaplib
import pandas as pd
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from openai import OpenAI
from pydantic import BaseModel
import smtplib
from datetime import datetime, timedelta

NUMBER_OF_EMAILS_TO_FETCH = 2
ASSISTANT_ID = "asst_BINPnxLsWnBKgDwvrY0ztWal"
MAX_FETCHES_PER_SESSION = 5
SESSION_TIMEOUT = timedelta(minutes=60)  # 60 minutes timeout

st.set_page_config(page_title="Your Email Buddy", layout="wide")

# Introductory Text
st.title("Your Email Buddy")
st.write(f"""
This application connects to your email inbox, fetches unread emails, and uses ChatGPT to analyze them. 
For each email, the app provides an importance score, a short summary, and a draft response. 
You can send the draft response back to the email sender, which would also mark the email as read in your inbox.
Since I am out of free OpenAI credits, this app is running on my personal credits. This app is therefore limited to a maximum of {NUMBER_OF_EMAILS_TO_FETCH} emails per run (use it with care please).
An example connection has been provided for you to test the app with dummy data.
Use this tool to manage your inbox more efficiently and respond to important emails faster.
GLHF!
""")

st.sidebar.header("Settings")

# Checkbox for using example connection
use_example = st.sidebar.checkbox("Use example connection", value=False)

# Configuration parameters
if use_example:
    IMAP_SERVER = st.secrets["imap_server"]
    EMAIL_ACCOUNT = st.secrets["email_account"]
    PASSWORD = st.secrets["email_password"]
    OPENAI_API_KEY = st.secrets["openai_api_key"]
else:
    IMAP_SERVER = st.sidebar.text_input("IMAP Server", "", help="The address of your email provider's IMAP server. [Learn more](https://support.google.com/mail/answer/7126229).")
    EMAIL_ACCOUNT = st.sidebar.text_input("Email Account", "", help="Your full email address. For example, 'yourname@gmail.com'.")
    PASSWORD = st.sidebar.text_input("Password", type="password", help="The password for your email account. If you're using Gmail, you might need an [App Password](https://support.google.com/accounts/answer/185833).")
    OPENAI_API_KEY = st.sidebar.text_input("OpenAI API Key", type="password", help="Your OpenAI API key. [Get your API key here](https://platform.openai.com/account/api-keys).")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


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
            'ID': email_id.decode('utf-8'),
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


def process_emails_and_create_ui(df):
    importance_scores = []
    summaries = []
    responses = []

    for idx, row in df.iterrows():
        # Create a thread
        thread = client.beta.threads.create()

        # Create a new message in the thread
        client.beta.threads.messages.create(
            thread_id=thread.id,
            content=row['Content'],
            role="user"
        )

        # Run the assistant with the created message
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # Poll for completion of the run
        while run.status == "queued" or run.status == "in_progress":
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )
            time.sleep(0.5)

        response = client.beta.threads.messages.list(thread_id=thread.id, order="asc")
        response_json = json.loads(response.data[1].content[0].text.value)

        importance_scores.append(response_json['importance'])
        summaries.append(response_json['summary'])
        responses.append(response_json['response'])

        # Create expander with processed information
        importance_emoji = "🔥" if response_json['importance'] == 5 else \
            "🔴" if response_json['importance'] == 4 else \
                "🟠" if response_json['importance'] == 3 else \
                    "🟡" if response_json['importance'] == 2 else \
                        "🟢"

        with st.expander(response_json['summary'], icon=importance_emoji):
            st.write(f"**From:** {row['From']}")
            st.write(f"**Date:** {row['Date']}")
            st.write(f"**Subject:** {row['Subject']}")
            st.write(f"**Original Content:** {row['Content']}")

            draft_response = st.text_area("Edit draft response:", value=response_json['response'], key=f"response_{idx}", height=200)

            if st.button(f"Send ✉️", key=f"send_{idx}"):
                with st.spinner(f"Sending reply..."):
                    success = send_email(row['From'], row['Subject'], draft_response)
                if success:
                    with st.spinner(f"Marking email from {row['From']} as read..."):
                        mark_as_read(row['ID'])
                    st.success(f"Response sent to {row['From']}")
                    st.session_state.processed_emails = st.session_state.processed_emails.drop(idx)
                    st.rerun()  # Rerun the app to update the interface

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


# Rate limit check
if 'last_fetch_time' not in st.session_state:
    st.session_state.last_fetch_time = datetime.now()
    st.session_state.fetch_count = 0


# Check rate limit
def check_rate_limit():
    now = datetime.now()
    if (now - st.session_state.last_fetch_time) > SESSION_TIMEOUT:
        st.session_state.last_fetch_time = now
        st.session_state.fetch_count = 0

    if st.session_state.fetch_count >= MAX_FETCHES_PER_SESSION:
        st.warning("You have reached the maximum number of fetches allowed in this session. Please try again later.")
        return False
    st.session_state.fetch_count += 1
    return True


# Streamlit app workflow
if (st.sidebar.button('Go!') and check_rate_limit()) or 'already_started' in st.session_state:
    if 'unread_emails' not in st.session_state:
        with st.spinner("Fetching unread emails..."):
            mail = connect_to_email()
            st.session_state.unread_emails = fetch_unread_emails(mail, NUMBER_OF_EMAILS_TO_FETCH)
            mail.logout()
        st.session_state.already_started = True

    if st.session_state.unread_emails:
        df = pd.DataFrame(st.session_state.unread_emails)
        with st.expander("Unread Emails"):
            st.dataframe(df)
        if 'processed_emails' not in st.session_state:
            with st.spinner("Analyzing emails..."):
                st.session_state.processed_emails = process_emails_and_create_ui(df)

    else:
        st.info("No unread emails found.")
