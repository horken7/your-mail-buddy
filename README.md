Your Mail Buddy
===============

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://your-mail-buddy.streamlit.app/)

Your Mail Buddy is a Streamlit-based application designed to help you efficiently manage your email inbox. This app connects to your email account, fetches unread emails, and leverages OpenAI's GPT models to analyze and generate personalized responses. The application offers features such as email importance scoring, email summarization, and the ability to send crafted replies directly from the app.
   
# Installation

## Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

## Install dependencies:

```bash
pip install -r requirements.txt
```

## Set up Streamlit secrets: 
You can either setup Streamlit secrets or take these secrets as user input in the UI.

Add your configuration to `.streamlit/secrets.toml`:

```
[default]
imap_server = "<your-imap-server>"
email_account = "<your-email-account>"
email_password = "<your-email-password>"
openai_api_key = "<your-openai-api-key>"
```

- IMAP Server: The address of your email provider's IMAP server. [Learn more](https://support.google.com/mail/answer/7126229).
- Email Account: Your full email address. For example, 'yourname@gmail.com'.
- Email Password: The password for your email account. If you're using Gmail, you might need an [App Password](https://support.google.com/accounts/answer/185833).
- OpenAI API Key: Your OpenAI API key. [Get your API key here](https://platform.openai.com/account/api-keys).

## Run the Application

```bash
streamlit run app.py
```
