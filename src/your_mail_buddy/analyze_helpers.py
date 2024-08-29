import json
import time
from json import JSONDecodeError

import streamlit as st


def analyze_email(content, client, assistant_id, max_fetch_attempts):
    # Create a thread
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id, content=content, role="user"
    )

    # Run the assistant
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant_id
    )

    attempt = 0
    info_placeholder = st.empty()  # Placeholder for the info bar

    while attempt < max_fetch_attempts:
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run.status == "failed":
            attempt += 1
            if attempt < max_fetch_attempts:
                info_placeholder.info(
                    f"Slow response due to OpenAI rate limiting. Retrying, {max_fetch_attempts - attempt} "
                    f"attempts left..."
                )
                time.sleep(21)
                run = client.beta.threads.runs.create(
                    thread_id=thread.id, assistant_id=assistant_id
                )
            else:
                # Final failure response
                info_placeholder.empty()  # Clear the info bar
                return {
                    "importance": 0,
                    "summary": "Analysis failed, problems communicating with OpenAI",
                    "response": run.last_error.message,
                }
        elif run.status == "completed":
            info_placeholder.empty()  # Clear the info bar
            response = client.beta.threads.messages.list(
                thread_id=thread.id, order="asc"
            )
            try:
                response_json = json.loads(response.data[-1].content[0].text.value)
                return response_json
            except JSONDecodeError:
                return {
                    "importance": 0,
                    "summary": "Analysis failed, problems communicating with OpenAI",
                    "response": f"Failed to parse: {response.data[-1].content[0].text.value}",
                }
        else:
            time.sleep(0.5)

    # If it exits the loop without returning, assume it failed
    info_placeholder.empty()  # Clear the info bar
    return {
        "importance": 0,
        "summary": "Analysis failed, problems communicating with OpenAI",
        "response": "Analysis failed, problems communicating with OpenAI",
    }
