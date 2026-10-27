import os
import json
import sys
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

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(base_dir, "config.json")
STATE_FILE = os.path.join(base_dir, "state.json")
TOKEN_FILE = os.path.join(base_dir, "token.json")
CLIENT_SECRET_FILE = os.path.join(base_dir, "client_secret.json")
#TOKEN_FILE = os.path.join(base_dir, "token_ii.json")
#CLIENT_SECRET_FILE = os.path.join(base_dir, "client_secret_ii.json")
LOG_FILE = os.path.join(base_dir, "bot.log")
replied_comment_ids = set()
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
        creds = flow.run_local_server()
        save_json(TOKEN_FILE, json.loads(creds.to_json()))

    return build("youtube", "v3", credentials=creds)


# ---------- COMMENTS ----------
def fetch_comments(youtube, config, last_check):
    params = {
        "part": "snippet,replies",
        "maxResults": 100,
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
            if item["snippet"]["topLevelComment"]["snippet"]["publishedAt"] < last_check:
                return comments
            comments.append(item)
        request = youtube.commentThreads().list_next(request, response)
    #print(json.dumps(comments, indent=4))
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
    generate_content_config = types.GenerateContentConfig(
        system_instruction=[
            types.Part.from_text(text=ai_cfg["system_prompt"]),
        ],
    )
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    return response.text


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
    if comment_id in replied_comment_ids:
        return

    youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": comment_id,
                "textOriginal": message
            }
        }
    ).execute()
    replied_comment_ids.add(comment_id)


# ---------- MAIN ----------
def main():

    header()
    info("Authenticating with YouTube...")
    youtube = authenticate()
    success("Authentication successful")

    my_channel_id = youtube.channels().list(
        part="id",
        mine=True
    ).execute()["items"][0]["id"]
    logging.info("Bot started")

    config = load_json(CONFIG_FILE, {})
    ai_cfg = config["ai"]

    state = load_json(STATE_FILE, {
        "replies_this_hour": 0,
        "hour_start": datetime.now(timezone.utc).isoformat()
    })
    show_config(config, state)
    divider()



    while True:
        try:
            now = datetime.now(timezone.utc)

            hour_start = datetime.fromisoformat(state["hour_start"])
            if now - hour_start >= timedelta(hours=1):
                state["replies_this_hour"] = 0
                state["hour_start"] = now.isoformat()

            if state["replies_this_hour"] >= config["max_replies_per_hour"]:
                status("Hourly limit reached. Sleeping...")
                time.sleep(60)
                continue

            status("Scanning comments...")
            comments = fetch_comments(youtube, config, state.get("last_checked", "2026-01-13T00:00:00Z"))
            success(f"Fetched {len(comments)} comments")

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
                status(f"Waiting {delay}s before replying...")
                time.sleep(delay)

                reply_text = generate_gemini_ai_reply(top_comment["textDisplay"], ai_cfg)
                reply_to_comment(youtube, top_comment_id, reply_text)
                success("Reply sent successfully")

                state["replies_this_hour"] += 1
                logging.info(f"Replied to {top_comment_id}")

            state["last_checked"] = now.isoformat()
            save_json(STATE_FILE, state)

            time.sleep(config["poll_interval_seconds"])

        except Exception as e:
            logging.exception(e)
            time.sleep(60)

def premium(license_key):
    machine_id = "0023456789"
    call_url = "https://json-key-checker.emdi-osuji.workers.dev"
    response = requests.get(f"{call_url}?key={license_key}&machine={machine_id}").json()

    return response.get("valid"), response.get("reason")


if __name__ == "__main__":
    is_valid, reason = premium("asd345_access")
    if is_valid:
        main()
    else:
        print("License validation failed.")
        print("Please contact the developer to activate this software.")
        input("Press ENTER to exit...")

