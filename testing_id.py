from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def print_channel_info():
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret_ii.json", SCOPES
    )
    credentials = flow.run_local_server(port=0)

    youtube = build("youtube", "v3", credentials=credentials)

    request = youtube.channels().list(
        part="id,snippet",
        mine=True
    )
    response = request.execute()

    channel = response["items"][0]
    print("Channel Name:", channel["snippet"]["title"])
    print("Channel ID:", channel["id"])

if __name__ == "__main__":
    print_channel_info()
