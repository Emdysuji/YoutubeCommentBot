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
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ================= CONFIG =================
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
    #base_dir = DATA_DIR = "/data"
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    #base_dir = DATA_DIR = "/data"

CONFIG_FILE = os.path.join(base_dir, "config.json")
STATE_FILE = os.path.join(base_dir, "state.json")
TOKEN_FILE = os.path.join(base_dir, "token.json")
CLIENT_SECRET_FILE = os.path.join(base_dir, "client_secret.json")
LOG_FILE = os.path.join(base_dir, "bot.log")

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


#======================================================
# ---------------- LOCAL SERVER FOR OAUTH ----------------
class OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        if "code" in params:
            OAuthHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authentication complete. You can close this tab.</h1></body></html>")
        else:
            self.send_response(400)
            self.end_headers()

def get_auth_code(client_info, redirect_uri):
    parsed_uri = urlparse(redirect_uri)
    server_address = (parsed_uri.hostname, parsed_uri.port or 8080)
    httpd = HTTPServer(server_address, OAuthHandler)

    scope_str = " ".join(SCOPES)
    auth_url = (
        f"{client_info['auth_uri']}?"
        f"client_id={client_info['client_id']}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={scope_str}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    webbrowser.open(auth_url)
    print(f"Waiting for authentication on {redirect_uri}...")
    httpd.handle_request()
    if OAuthHandler.auth_code is None:
        raise Exception("Failed to get auth code")
    return OAuthHandler.auth_code

def exchange_code_for_tokens(client_info, code, redirect_uri):
    token_url = client_info["token_uri"]
    data = {
        "code": code,
        "client_id": client_info["client_id"],
        "client_secret": client_info["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    return resp.json()

def refresh_access_token(client_info, refresh_token):
    token_url = client_info["token_uri"]
    data = {
        "client_id": client_info["client_id"],
        "client_secret": client_info["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    return resp.json()["access_token"]

# ---------------- REST CLIENT WRAPPER ----------------
class ResourceMethod:
    def __init__(self, client, resource_name, method_name):
        self.client = client
        self.resource_name = resource_name
        self.method_name = method_name
        self.params = {}
        self.body = None

    def __call__(self, **kwargs):
        self.params = kwargs
        self.body = kwargs.pop("body", None)
        return self

    def execute(self):
        url = f"https://www.googleapis.com/youtube/v3/{self.resource_name}"
        headers = {
            "Authorization": f"Bearer {self.client.access_token}",
            "Content-Type": "application/json"
        }

        method = self.method_name.lower()

        if method == "list":
            resp = requests.get(url, headers=headers, params=self.params)

        elif method == "insert":
            resp = requests.post(url, headers=headers, params=self.params, json=self.body)

        elif method == "delete":
            resp = requests.delete(url, headers=headers, params=self.params)

        elif method == "update":
            resp = requests.put(url, headers=headers, params=self.params, json=self.body)

        else:
            raise NotImplementedError(f"Unsupported method: {self.method_name}")

        resp.raise_for_status()
        return resp.json()


class Resource:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def __getattr__(self, method_name):
        return ResourceMethod(self.client, self.name, method_name)


class Resource:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def __getattr__(self, method_name):
        return ResourceMethod(self.client, self.name, method_name)

class YouTubeClient:
    def __init__(self, access_token):
        self.access_token = access_token

    def __getattr__(self, resource_name):
        return Resource(self, resource_name)

# ---------------- MAIN AUTH FUNCTION ----------------
def authenticates():
    # Load client secrets
    with open(CLIENT_SECRET_FILE, "r") as f:
        data = json.load(f)
    client_info = data["installed"]
    redirect_uri = client_info["redirect_uris"][0]

    # Load existing tokens
    tokens = load_json(TOKEN_FILE, None)
    if tokens:
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
    else:
        code = get_auth_code(client_info, redirect_uri)
        tokens = exchange_code_for_tokens(client_info, code, redirect_uri)
        save_json(TOKEN_FILE, tokens)
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")

    # Check if token is valid
    info_resp = requests.get(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        params={"access_token": access_token}
    )
    if info_resp.status_code != 200 and refresh_token:
        access_token = refresh_access_token(client_info, refresh_token)
        tokens["access_token"] = access_token
        save_json(TOKEN_FILE, tokens)

    # Return a build()-like object
    return YouTubeClient(access_token)

#===================================================



# ---------- AUTH ----------
def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRET_FILE, SCOPES
        )
        creds = flow.run_local_server(open_browser=False)
        save_json(TOKEN_FILE, json.loads(creds.to_json()))

    return build("youtube", "v3", credentials=creds)


def sauthenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        auth_url, _ = flow.authorization_url(prompt='consent')
        print("\nVisit this URL in your browser:")
        print(auth_url)
        code = input("\nEnter the code from Google: ")
        creds = flow.fetch_token(code=code)
        save_json(TOKEN_FILE, json.loads(creds.to_json()))
        print("\nLogin successful. Token saved.")

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
            comments = fetch_comments(youtube, config)
            comments = [c for c in comments if
                        c["snippet"]["topLevelComment"]["snippet"]["publishedAt"] > state.get("last_checked", "1970-01-01T00:00:00Z")]
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

