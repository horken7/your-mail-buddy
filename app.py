import json
import time

import streamlit as st
import imaplib
import pandas as pd
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr
from openai import OpenAI
import smtplib
from datetime import datetime, timedelta

NUMBER_OF_EMAILS_TO_FETCH = 5
ASSISTANT_ID = "asst_BINPnxLsWnBKgDwvrY0ztWal"
MAX_FETCHES_PER_SESSION = 5
SESSION_TIMEOUT = timedelta(minutes=60)
MAX_FETCH_ATTEMPTS = st.secrets.get("max_fetch_attempts", 7)

st.set_page_config(page_title="Your Email Buddy", layout="wide")

# Introductory Text
st.title("Your Email Buddy")
st.write(f"""
Your personal email assistant, helping you manage your inbox more efficiently and craft personalized responses to important emails.
""")

with st.expander("Info", icon=":material/info:"):
    st.write(f"""
    This application connects to your email inbox, fetches unread emails, and uses ChatGPT to analyze them. 
    For each email, the app provides an importance score, a short summary, and a draft response. 
    The draft response is adapted to my writing style in previously sent emails, and can be extended to automatically adapt to any users writing style. 
    You can send the draft response back to the email sender, which would also mark the email as read in your inbox.
    An example connection has been provided for you to test the app with dummy data.
    The example connection is running on my personal OpenAI credits. This app is therefore limited to a maximum of {NUMBER_OF_EMAILS_TO_FETCH} emails per run (use it with care please).
    OpenAI unfortunately have very strict rate limits in the low paid tiers, so please be patient with the app (yes it will be slow, but it works).
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

        email_from_full = msg.get('From')
        email_from = parseaddr(email_from_full)[1]  # Extract just the email address

        email_date = parsedate_to_datetime(msg.get('Date')).strftime('%Y-%m-%d %H:%M:%S')
        email_content = get_email_content(msg)

        emails.append({
            'ID': email_id.decode('utf-8'),
            'From': email_from,
            'To': msg.get('To'),
            'Date': email_date,
            'Subject': email_subject,
            'Content': email_content
        })
    return emails


def get_email_content(msg):
    if msg.is_multipart():
        content = []
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                content.append(part.get_payload(decode=True).decode())
        return ''.join(content)
    else:
        return msg.get_payload(decode=True).decode()


def process_emails_and_create_ui(df):
    email_results = []

    for idx, row in df.iterrows():
        response_json = analyze_email(row['Content'])

        importance_emoji = get_importance_emoji(response_json['importance'])

        with st.expander(response_json['summary'], icon=importance_emoji):
            if response_json['importance'] == 0:
                st.error(response_json['response'])
            else:
                st.write(f"**From:** {row['From']}")
                st.write(f"**Date:** {row['Date']}")
                st.write(f"**Subject:** {row['Subject']}")
                st.write(f"**Original Content:** {row['Content']}")

                draft_response = st.text_area("Edit draft response:", value=response_json['response'],
                                              key=f"response_{idx}", height=200)

                if st.button(f"Send ✉️", key=f"send_{idx}"):
                    if send_email(row['From'], row['Subject'], draft_response):
                        mark_as_read(row['ID'])
                        st.success(f"Response sent to {row['From']}")
                        st.session_state.processed_emails = st.session_state.processed_emails.drop(idx)
                        st.rerun()

        email_results.append({
            'Importance Score': response_json['importance'],
            'Summary': response_json['summary'],
            'Draft Response': response_json['response']
        })

    df_result = df.copy()
    df_result = df_result.assign(**pd.DataFrame(email_results))
    return df_result


def analyze_email(content):
    # Create a thread
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(thread_id=thread.id, content=content, role="user")

    # Run the assistant
    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)

    attempt = 0
    info_placeholder = st.empty()  # Placeholder for the info bar

    while attempt < MAX_FETCH_ATTEMPTS:
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run.status == "failed":
            attempt += 1
            if attempt < MAX_FETCH_ATTEMPTS:
                info_placeholder.info(f"Slow response due to OpenAI rate limiting. Retrying, {MAX_FETCH_ATTEMPTS - attempt} attempts left...")
                time.sleep(21)
                run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)
            else:
                # Final failure response
                info_placeholder.empty()  # Clear the info bar
                return {
                    'importance': 0,
                    'summary': "Analysis failed, problems communicating with OpenAI",
                    'response': run.last_error.message
                }
        elif run.status == "completed":
            info_placeholder.empty()  # Clear the info bar
            response = client.beta.threads.messages.list(thread_id=thread.id, order="asc")
            response_json = json.loads(response.data[-1].content[0].text.value)
            return response_json
        else:
            time.sleep(0.5)

    # If it exits the loop without returning, assume it failed
    info_placeholder.empty()  # Clear the info bar
    return {
        'importance': 0,
        'summary': "Analysis failed, problems communicating with OpenAI",
        'response': "Analysis failed, problems communicating with OpenAI"
    }


def get_importance_emoji(importance):
    emojis = {
        5: "🔥",
        4: "🔴",
        3: "🟠",
        2: "🟡",
        1: "🟢",
        0: "❌"
    }
    return emojis.get(importance, "🟢")


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
        # todo disable df print, not necessary
        # with st.expander("Unread Emails"):
        #     st.dataframe(df)
        if 'processed_emails' not in st.session_state:
            with st.spinner("Analyzing emails..."):
                st.session_state.processed_emails = process_emails_and_create_ui(df)

    else:
        st.info("No unread emails found.")
