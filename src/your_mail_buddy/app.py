from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from openai import OpenAI

from .analyze_helpers import analyze_email
from .email_helpers import (connect_to_email, fetch_unread_emails,
                            mark_as_read, send_email)
from .utils import check_rate_limit, get_importance_emoji

NUMBER_OF_EMAILS_TO_FETCH = 5
ASSISTANT_ID = "asst_BINPnxLsWnBKgDwvrY0ztWal"
MAX_FETCHES_PER_SESSION = 5
SESSION_TIMEOUT = timedelta(minutes=60)
MAX_FETCH_ATTEMPTS = st.secrets.get("max_fetch_attempts", 7)

st.set_page_config(page_title="Your Email Buddy", layout="wide")

# Introductory Text
st.title("Your Mail Buddy")
st.write(
    """
Your personal email assistant, helping you manage your inbox more efficiently and craft personalized responses to
 important emails.
"""
)

with st.expander("Info", icon=":material/info:"):
    st.write(
        f"""
    This application connects to your email inbox, fetches unread emails, and uses ChatGPT to analyze them.
    For each email, the app provides an importance score, a short summary, and a draft response.
    The draft response is adapted to my writing style in previously sent emails, and can be extended to automatically
     adapt to any users writing style.
    You can send the draft response back to the email sender, which would also mark the email as read in your inbox.
    An example connection has been provided for you to test the app with dummy data.
    The example connection is running on my personal OpenAI credits. This app is therefore limited to a maximum of
 {NUMBER_OF_EMAILS_TO_FETCH} emails per run (use it with care please).
    OpenAI unfortunately have very strict rate limits in the low paid tiers, so please be patient with the app (yes it
     will be slow, but it works).
    GLHF!
    """
    )

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
    IMAP_SERVER = st.sidebar.text_input(
        "IMAP Server",
        "",
        help="The address of your email provider's IMAP server. "
        "[Learn more](https://support.google.com/mail/answer/7126229).",
    )
    EMAIL_ACCOUNT = st.sidebar.text_input(
        "Email Account",
        "",
        help="Your full email address. For example, 'yourname@gmail.com'.",
    )
    PASSWORD = st.sidebar.text_input(
        "Password",
        type="password",
        help="The password for your email account. If you're using Gmail, you might need an "
        "[App Password](https://support.google.com/accounts/answer/185833).",
    )
    OPENAI_API_KEY = st.sidebar.text_input(
        "OpenAI API Key",
        type="password",
        help="Your OpenAI API key. [Get your API key here](https://platform.openai.com/account/api-keys).",
    )

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


def process_emails_and_create_ui(df_unprocessed):
    email_results = []

    for idx, row in df_unprocessed.iterrows():
        response_json = analyze_email(
            row["Content"], client, ASSISTANT_ID, MAX_FETCH_ATTEMPTS
        )

        importance_emoji = get_importance_emoji(response_json["importance"])

        with st.expander(response_json["summary"], icon=importance_emoji):
            if response_json["importance"] == 0:
                st.error(response_json["response"])
            else:
                st.write(f"**From:** {row['From']}")
                st.write(f"**Date:** {row['Date']}")
                st.write(f"**Subject:** {row['Subject']}")
                st.write(f"**Original Content:** {row['Content']}")

                draft_response = st.text_area(
                    "Edit draft response:",
                    value=response_json["response"],
                    key=f"response_{idx}",
                    height=200,
                )

                if st.button("Send ✉️", key=f"send_{idx}"):
                    if send_email(
                        row["From"],
                        row["Subject"],
                        draft_response,
                        EMAIL_ACCOUNT,
                        PASSWORD,
                    ):
                        mark_as_read(row["ID"], IMAP_SERVER, EMAIL_ACCOUNT, PASSWORD)
                        st.success(f"Response sent to {row['From']}")
                        st.session_state.processed_emails = (
                            st.session_state.processed_emails.drop(idx)
                        )
                        st.rerun()

        email_results.append(
            {
                "Importance Score": response_json["importance"],
                "Summary": response_json["summary"],
                "Draft Response": response_json["response"],
            }
        )

    df_result = df_unprocessed.copy()
    df_result = df_result.assign(**pd.DataFrame(email_results))
    return df_result


# Rate limit check
if "last_fetch_time" not in st.session_state:
    st.session_state.last_fetch_time = datetime.now()
    st.session_state.fetch_count = 0

# Streamlit app workflow
if (
    st.sidebar.button("Go!")
    and check_rate_limit(SESSION_TIMEOUT, MAX_FETCHES_PER_SESSION)
) or "already_started" in st.session_state:
    if "unread_emails" not in st.session_state:
        with st.spinner("Fetching unread emails..."):
            mail = connect_to_email(IMAP_SERVER, EMAIL_ACCOUNT, PASSWORD)
            st.session_state.unread_emails = fetch_unread_emails(
                mail, NUMBER_OF_EMAILS_TO_FETCH
            )
            mail.logout()
        st.session_state.already_started = True

    if st.session_state.unread_emails:
        df = pd.DataFrame(st.session_state.unread_emails)
        if "processed_emails" not in st.session_state:
            with st.spinner("Analyzing emails..."):
                st.session_state.processed_emails = process_emails_and_create_ui(df)

    else:
        st.info("No unread emails found.")
