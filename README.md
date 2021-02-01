# FlagBot
 ~~Korea~~Lethal Guild Bro
 
 (A bot to track Flag Race points in MapleStory)
 
 This is a Discord bot, not a bot to run flag race for you. Maybe try getting good instead if thats what you came here for.

## Requirements
* Python 3.x (Should work with them all ¯\\_(ツ)_/¯ )
* discord.py
* google-api-python-client
* google-auth-httplib2
* google-auth-oauthlib
* aioschedule
* A [google service account](https://cloud.google.com/iam/docs/creating-managing-service-accounts) with saved json credentials
* A copy of [this](https://docs.google.com/spreadsheets/d/1Xlmh_GhN2MoL8qauUg6bvAy92JtySKUZtEkmeZyyXWA/edit?usp=sharing) spreadsheet
* A [discord application](https://discord.com/developers)

## Instructions
1. Download repo
2. Fill in `sample_config.py` and rename to `config.py`
3. Run `main.py`

## Tracking Flag points
1. Have the administrator designate a point tracking channel with `!trackChannel <channel id/channel ping/channel name>`
2. After every race, the bot will open an hour long window for people to post their points. Note this is points rather than place.
3. Bot will create a fresh sheet weekly


## Questions?
 IGN: `Lostara` (reboot)
 
