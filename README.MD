YouTube Reply Bot (EXE)

This program automatically reads YouTube comments and replies to them using AI.
You do not write code. You only configure files and run the EXE.

1. Folder Structure (IMPORTANT)

After setup, your folder must look exactly like this:
/YouTubeBot/
│
├─ YouTube Reply Bot.exe
├─ config.json
├─ client_secret.json
├─ README.txt
│
├─ token.json        (auto-created)
├─ state.json        (auto-created)
├─ bot.log           (auto-created)

You only manually provide:
client_secret.json


2. What Each File Does
YouTube Reply Bot.exe

The bot itself.
Double-click to run.

client_secret.json ❗ REQUIRED
This is your YouTube API OAuth file.

You must:
- Go to Google Cloud Console
- Enable YouTube Data API v3
- Create OAuth Client ID
- Download the JSON
- Rename it to:  client_secret.json
- but it looks like you already have one so just rename it to: client_secret.json

Put it in the same folder as the EXE.
⚠️ Without this file, the bot will not start.

config.json ❗ REQUIRED
This controls how the bot behaves.

Example:
{
  "mode": "channel",
  "channel_id": "Uxxxxxxxxxxxx",
  "video_id": "",
  "poll_interval_seconds": 60,
  "max_replies_per_hour": 20,
  "reply_delay_seconds": [15, 60],

  "ai": {
    "provider": "Google",
    "api_key": "YOUR_GEMINI_API_KEY",
    "model": "gemini-2.5-flash",
    "system_prompt": "You are a YouTube content creator replying naturally to comments. Replies must sound human, friendly, and short."
  }
}


3. config.json Settings Explained (Simple)

mode
- "mode": "channel"
- Bot replies to all comments on your channel.

OR

- "mode": "video"
- Bot replies to one specific video.

channel_id
- Used only if mode = "channel"
- Your YouTube Channel ID (starts with U).

video_id
- Used only if mode = "video"
- The YouTube video ID.

poll_interval_seconds
- How often the bot checks for new comments.
- Example:
    60 = check every 1 minute (every whole number is a second)

max_replies_per_hour
- Safety limit to avoid spam / bans.
- Example:
    20 = max 20 replies per hour

reply_delay_seconds
- Random delay before replying (looks human).
- Example:
    [15, 60] = wait 15–60 seconds before replying

ai.api_key
- Your Google Gemini API key.
- You must create this yourself from: Google AI Studio
- But you already have that

ai.system_prompt
- Controls reply style.
- Change this if you want:
    - More professional replies
    - Short replies
    - Funny replies


4. First Run (Very Important)

- Double-click YouTube Reply Bot.exe
- A browser window opens
- Log into the YouTube account you want the bot to reply from
- Click Allow
- This happens ONLY ONCE.
- After that:
    - token.json is created
    - No more browser popups


5. What the Bot Does Automatically

✔ Reads new comments
✔ Skips comments you already replied to
✔ Skips your own comments
✔ Generates AI replies
✔ Respects rate limits
✔ Saves state (won’t reply twice)
✔ Runs forever until closed


6. Files Created Automatically (Do NOT Touch)

- token.json
    Stores YouTube login session.

- state.json
    Tracks:
    - Last checked time
    - Replies per hour

-bot.log
    Error and activity log (for debugging only).


7. How to Stop the Bot
- Close the terminal window
- OR
- Press CTRL + C
Safe to restart anytime.


8. Common Problems
- Bot closes immediately

❌ Missing client_secret.json
❌ Wrong file name
❌ Invalid API keys

Bot replies nothing

✔ No new comments
✔ Hourly limit reached
✔ Already replied before

9. Important Rules

- Keep all files in the same folder
- Do not rename files
- Do not delete token.json
- Do not run multiple copies


10. Summary (TL;DR)

- Put YouTube Reply Bot.exe, config.json, client_secret.json in one folder
- Edit config.json
- Run the EXE
- Authorize YouTube once
- Done
