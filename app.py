import streamlit as st
import imaplib
import pandas as pd
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from openai import OpenAI
from pydantic import BaseModel

IMAP_SERVER = 'imap.gmail.com'
EMAIL_ACCOUNT = "yourmailbuddy@gmail.com"
PASSWORD = ""
OPENAI_API_KEY = ""
client = OpenAI(api_key=OPENAI_API_KEY)


# Functions
def connect_to_email():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, PASSWORD)
    return mail


def fetch_unread_emails(mail):
    mail.select('inbox')
    status, data = mail.search(None, 'UNSEEN')
    if status != 'OK':
        st.error('Error fetching emails')
        return []
    email_ids = data[0].split()
    emails = []
    for email_id in email_ids:
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
        "Provide a short and concise one-sentence summary of the email."
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
email_account = st.sidebar.text_input("Email Account", EMAIL_ACCOUNT)
password = st.sidebar.text_input("Password", PASSWORD, type="password")
api_key = st.sidebar.text_input("OpenAI API Key", OPENAI_API_KEY, type="password")

if st.sidebar.button('Fetch and Process Unread Emails'):
    with st.spinner("Connecting to email server..."):
        mail = connect_to_email()
    with st.spinner("Fetching unread emails..."):
        unread_emails = fetch_unread_emails(mail)
        mail.logout()

    if unread_emails:
        df = pd.DataFrame(unread_emails[:4]) # todo filter to limit volume here
        with st.spinner("Analyzing emails..."):
            df = add_importance_and_response(df)

        st.success("Emails processed successfully!")

        # Display the DataFrame
        st.subheader("📋 Processed Emails")
        st.dataframe(df)
    else:
        st.info("No unread emails found.")
