from datetime import datetime
import streamlit as st


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


# Check rate limit
def check_rate_limit(session_timeout, max_fetches_per_session):
    now = datetime.now()
    if (now - st.session_state.last_fetch_time) > session_timeout:
        st.session_state.last_fetch_time = now
        st.session_state.fetch_count = 0

    if st.session_state.fetch_count >= max_fetches_per_session:
        st.warning("You have reached the maximum number of fetches allowed in this session. Please try again later.")
        return False
    st.session_state.fetch_count += 1
    return True