import streamlit as st
import requests
import json
import pandas as pd
import os
import time
from datetime import datetime


RASA_API_URL = "http://localhost:5005/webhooks/rest/webhook"
LOG_FILE = "chat_logs.csv"

def log_interaction(user_input, bot_response):
    """Logs user query and bot response to a CSV file using Pandas."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = pd.DataFrame(
        [[timestamp, user_input, bot_response]],
        columns=["Timestamp", "User", "Bot"]
    )
    if not os.path.isfile(LOG_FILE):
        new_data.to_csv(LOG_FILE, index=False)
    else:
        new_data.to_csv(LOG_FILE, mode='a', header=False, index=False)

def reset_conversation():
    st.session_state.messages = []
    st.session_state.session_id = str(int(time.time()))
    st.session_state.landing_done = False
    st.session_state.user_name = ""
    st.session_state.user_location = ""
    st.session_state.eco_preference = ""
    st.session_state.pending_buttons = []

st.set_page_config(page_title="Eco Trip Planner", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Navigation")
    if st.button("New Conversation"):
        reset_conversation()
        st.rerun()
    st.divider()
    st.header("Analytics Dashboard")
    if st.button("Clear Analytics Data"):
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
            st.success("Cleared!")
            st.rerun()
        else:
            st.warning("No data to clear.")
    if st.checkbox("Show Usage Stats"):
        if os.path.exists(LOG_FILE):
            try:
                df = pd.read_csv(LOG_FILE)
                st.metric("Total Interactions", len(df))
                st.write("### Recent Logs")
                st.dataframe(df.tail(5))
                # Bar chart added to match lecturer's analytics feature
                if 'User' in df.columns:
                    st.write("### Top Queries")
                    st.bar_chart(df['User'].value_counts().head(5))
            except Exception as e:
                st.error(f"Error reading logs: {e}")
        else:
            st.info("No logs yet!")

# ── Session state initialisation ──────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(int(time.time()))

if "pending_buttons" not in st.session_state:
    st.session_state.pending_buttons = []

if "landing_done" not in st.session_state:
    st.session_state.landing_done = False

if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if "user_location" not in st.session_state:
    st.session_state.user_location = ""

if "eco_preference" not in st.session_state:
    st.session_state.eco_preference = ""

# ── Landing form ──────────────────────────────────────────────────────────

if not st.session_state.landing_done:
    st.title("Eco Trip - Sustainable Travel Planner")
    st.markdown("#### Plan your carbon-conscious journey. Tell us a little about yourself to get started.")
    st.divider()

    with st.form("landing_form"):
        name = st.text_input("Your name", placeholder="e.g. Sarah")
        location = st.text_input("Your current location", placeholder="e.g. Berlin")
        eco_pref = st.selectbox(
            "Your eco priority",
            ["No preference", "Lowest carbon footprint", "Eco-certified accommodation", "Sustainable activities only"]
        )
        submitted = st.form_submit_button("Start Planning")

    if submitted:
        if not name.strip():
            st.warning("Please enter your name to continue.")
        else:
            st.session_state.user_name = name.strip()
            st.session_state.user_location = location.strip()
            st.session_state.eco_preference = eco_pref
            st.session_state.landing_done = True

            # Build personalised greeting using name and eco preference
            greeting = f"Hi {name.strip()}! I am your Eco-Travel Advisor."
            if location.strip():
                greeting += f" I can see you are travelling from {location.strip()}."
            if eco_pref != "No preference":
                greeting += f" Your eco priority is noted: {eco_pref}."

            # Send /start to Rasa to activate trip_form
            try:
                # Step 1: trigger trip_form via /start intent
                start_resp = requests.post(
                    RASA_API_URL,
                    json={"sender": st.session_state.session_id, "message": "/start"},
                    timeout=5
                )
                rasa_replies = start_resp.json()

                # Step 2: pre-fill origin slot if user gave a location
                if location.strip():
                    requests.post(
                        RASA_API_URL,
                        json={
                            "sender": st.session_state.session_id,
                            "message": location.strip()
                        },
                        timeout=5
                    )

                # Step 3: show greeting first
                st.session_state.messages.append(
                    {"role": "assistant", "content": greeting}
                )
                log_interaction("LANDING_FORM", greeting)

                # Step 4: show Rasa replies (skip origin prompt if we pre-filled it)
                for reply in rasa_replies:
                    if "text" in reply:
                        msg = reply["text"]
                        if location.strip() and "travelling from" in msg.lower():
                            continue
                        if location.strip() and "departure city" in msg.lower():
                            continue
                        st.session_state.messages.append(
                            {"role": "assistant", "content": msg}
                        )
                        log_interaction("RASA_START", msg)

            except Exception as e:
                # Fallback if Rasa is not yet running
                greeting += " Where would you like to travel to?"
                st.session_state.messages.append(
                    {"role": "assistant", "content": greeting}
                )
                log_interaction("LANDING_FORM", greeting)

            st.rerun()

# ── Main chat interface ───────────────────────────────────────────────────

else:
    st.title("Eco Trip - Sustainable Travel Planner")

    if st.session_state.user_name:
        caption = f"Welcome, {st.session_state.user_name}"
        if st.session_state.user_location:
            caption += f" - travelling from {st.session_state.user_location}"
        st.caption(caption)

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Render any pending quick-reply buttons
    # FIX: button key now includes index (i) to prevent DuplicateWidgetID errors on rerun
    if st.session_state.pending_buttons:
        with st.chat_message("assistant"):
            for i, btn in enumerate(st.session_state.pending_buttons):
                if st.button(
                    btn["title"],
                    key=f"btn_{i}_{btn['payload']}_{st.session_state.session_id}"
                ):
                    st.session_state.pending_buttons = []
                    payload_text = btn["payload"].replace("/", "")
                    st.session_state.messages.append({"role": "user", "content": btn["title"]})
                    try:
                        btn_response = requests.post(
                            RASA_API_URL,
                            json={"sender": st.session_state.session_id, "message": payload_text},
                            timeout=10
                        )
                        for br in btn_response.json():
                            if "text" in br:
                                st.session_state.messages.append(
                                    {"role": "assistant", "content": br["text"]}
                                )
                            if "buttons" in br:
                                st.session_state.pending_buttons = br["buttons"]
                    except Exception as e:
                        st.session_state.messages.append(
                            {"role": "assistant", "content": f"Connection error: {e}"}
                        )
                    st.rerun()

    # Main text input
    if prompt := st.chat_input("Where would you like to travel?"):
        st.session_state.pending_buttons = []
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            response = requests.post(
                RASA_API_URL,
                # sender is required so Rasa maintains conversation state across turns
                json={"sender": st.session_state.session_id, "message": prompt},
                timeout=10
            )
            response.raise_for_status()
            rasa_data = response.json()
            bot_text = ""

            if rasa_data:
                for r in rasa_data:
                    if "text" in r:
                        bot_text += r["text"] + "\n\n"
                        with st.chat_message("assistant"):
                            st.markdown(r["text"])
                    if "buttons" in r:
                        st.session_state.pending_buttons = r["buttons"]

                st.session_state.messages.append(
                    {"role": "assistant", "content": bot_text.strip()}
                )
                log_interaction(prompt, bot_text.strip())

            else:
                fallback_msg = "I am listening, but I did not catch that. Could you rephrase?"
                with st.chat_message("assistant"):
                    st.markdown(fallback_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": fallback_msg}
                )
                log_interaction(prompt, fallback_msg)

        except Exception as e:
            st.error(f"Connection Error: {e}")
