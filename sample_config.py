## Fill in your bots information, then rename to 'config.py'

## Discord Bot Token
TOKEN = 'YOUR_BOTS_TOKEN_HERE'

## Discord ID of the user which can manage the bot
ADMINS = [1234, 4567]

## Discord ID of the guild you want the bot to run in
GPQ_GUILD = 1234

## Discord ID of the guild you want to test the bot in
DEV_GUILD = 1234

## Discord ID of the channels you want the bot to respond to commands in (BOTH GPQ and DEV guilds)
GPQ_CHANNELS = [1234, 4567]

## Service account Cred file (for sheets auth)
CRED_FILE = "credentials.json"

## Google Cloud cred file (for OCR)
VISION_CRED_FILE = "vision_keyfile.json"

## ID of the google sheet for GPQ scores
GPQ_SHEET = "SHEET_ID_HERE"

## Flavor Text
GUILD_NAME = "Drowsy"
GUILD_CURRENCY = "Drowsy Dinero"
EMBED_IMAGE_URL = "https://cdn.discordapp.com/emojis/743215456839532604.png"

## PSQL DB info
## This should be environmental but IDC
DB_USER="USER"
GPQ_DB_NAME="DB_NAME"
DB_PASS="PASSWORD"
DB_ADDR="1.2.3.4"