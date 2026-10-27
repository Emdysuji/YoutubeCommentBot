import os
import json
import time
import random
import logging
from datetime import datetime, timedelta, timezone
import requests
from google import genai
from google.genai import types
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from cli import header, show_config, status, success, error, info, divider
from googleapiclient.errors import HttpError


# ================= CONFIG =================
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"
LOG_FILE = "bot.log"
# =========================================


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------- AUTH ----------
def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRET_FILE, SCOPES
        )
        creds = flow.run_local_server(port=0)
        save_json(TOKEN_FILE, json.loads(creds.to_json()))

    return build("youtube", "v3", credentials=creds)


# ---------- COMMENTS ----------
def fetch_comments(youtube, config):
    params = {
        "part": "snippet,replies",
        "maxResults": 50,
        "order": "time",
        "textFormat": "plainText"
    }

    if config["mode"] == "channel":
        params["allThreadsRelatedToChannelId"] = config["channel_id"]
    else:
        params["videoId"] = config["video_id"]

    comments = []
    request = youtube.commentThreads().list(**params)

    while request:
        response = request.execute()
        for item in response["items"]:
            comments.append(item)
        request = youtube.commentThreads().list_next(request, response)

    return comments

#-------checking if i already replied-------
def already_replied_by_me(comment_thread, my_channel_id):
    replies = comment_thread.get("replies", {}).get("comments", [])
    for r in replies:
        author = r["snippet"].get("authorChannelId", {}).get("value")
        if author == my_channel_id:
            return True
    return False

# ---------- AI ----------
def generate_gemini_ai_reply(comment_text, ai_cfg):
    client = genai.Client(api_key=ai_cfg['api_key'])
    model = ai_cfg["model"]
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=comment_text),],
        ),
    ]
    tools = [types.Tool(googleSearch=types.GoogleSearch()),]
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0,),
        tools=tools,
        system_instruction=[
            types.Part.from_text(text=ai_cfg["system_prompt"]),
        ],
    )

    reply_chunks = []
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        if chunk.text:
            reply_chunks.append(chunk.text)

    return "".join(reply_chunks).strip()

def generate_ai_reply(comment_text, ai_cfg):
    headers = {
        "Authorization": f"Bearer {ai_cfg['api_key']}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": ai_cfg["model"],
        "messages": [
            {"role": "system", "content": ai_cfg["system_prompt"]},
            {"role": "user", "content": comment_text}
        ],
        "temperature": 0.7,
        "max_tokens": 60
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


# ---------- REPLY ----------
def reply_to_comment(youtube, comment_id, message):
    youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": comment_id,
                "textOriginal": message
            }
        }
    ).execute()


# ---------- MAIN ----------
def main():
    config = load_json(CONFIG_FILE, {})
    ai_cfg = config["ai"]

    state = load_json(STATE_FILE, {
        "replies_this_hour": 0,
        "hour_start": datetime.now(timezone.utc).isoformat()
    })

    youtube = authenticate()
    my_channel_id = youtube.channels().list(
        part="id",
        mine=True
    ).execute()["items"][0]["id"]
    logging.info("Bot started")

    while True:
        try:
            now = datetime.now(timezone.utc)

            hour_start = datetime.fromisoformat(state["hour_start"])
            if now - hour_start >= timedelta(hours=1):
                state["replies_this_hour"] = 0
                state["hour_start"] = now.isoformat()

            if state["replies_this_hour"] >= config["max_replies_per_hour"]:
                time.sleep(60)
                continue

            comments = fetch_comments(youtube, config)
            comments = [c for c in comments if
                        c["snippet"]["topLevelComment"]["snippet"]["publishedAt"] > state.get("last_checked", "1970-01-01T00:00:00Z")]

            for thread in comments:
                top_comment = thread["snippet"]["topLevelComment"]["snippet"]
                top_comment_id = thread["snippet"]["topLevelComment"]["id"]
                author_channel = top_comment.get("authorChannelId", {}).get("value")

                if author_channel == my_channel_id:
                    continue

                if already_replied_by_me(thread, my_channel_id):
                    continue

                delay = random.randint(
                    config["reply_delay_seconds"][0],
                    config["reply_delay_seconds"][1]
                )
                time.sleep(delay)

                reply_text = generate_gemini_ai_reply(top_comment["textDisplay"], ai_cfg)
                reply_to_comment(youtube, top_comment_id, reply_text)

                state["replies_this_hour"] += 1
                logging.info(f"Replied to {top_comment_id}")

            state["last_checked"] = now.isoformat()
            save_json(STATE_FILE, state)

            time.sleep(config["poll_interval_seconds"])

        except Exception as e:
            logging.exception(e)
            time.sleep(60)

def generate_gemini_ai_reply(comment_text, ai_cfg):
    api_key = ai_cfg['api_key']
    model = ai_cfg["model"]
    generate_api= "streamGenerateContent"

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:{generate_api}?key={api_key}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"{ai_cfg['system_prompt']}: \n {comment_text} "
                    }
                ]
            }
        ],
        "generationConfig": {
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    # Combine all text from all chunks
    reply_text = ""
    for chunk in data:
        reply_text += chunk['candidates'][0]['content']['parts'][0]['text']

    return reply_text

if __name__ == "__main__":
    main()
