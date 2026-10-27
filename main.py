"""
youtube = authenticate()
my_channel_id = youtube.channels().list(part="id", mine=True).execute()["items"][0]["id"]
print(my_channel_id)

"""



import base64
import json
import os
from google import genai
from google.genai import types

CONFIG_FILE = "config.json"
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate(comment_text, ai_cfg):
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

if __name__ == "__main__":
    config = load_json(CONFIG_FILE, {})
    ai_cfg = config["ai"]
    generate()
