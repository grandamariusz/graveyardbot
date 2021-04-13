import discord, os, urllib.request, json, random, asyncio, requests, re, config
from discord.ext import tasks, commands
from osuapi import OsuApi, ReqConnector
from datetime import datetime
import musicbrainzngs as mb

intents = discord.Intents.default()
intents.members = True
intents.reactions = True
client = commands.Bot(command_prefix=config.prefix, intents=intents)

tmp_token=''
date=''

@client.event
async def on_ready():
    print("I'm ready")
    await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="87th dimension"))

@client.event
async def on_member_join(member):
    channel = client.get_channel(config.join_channel)
    await member.add_roles(discord.utils.get(member.guild.roles, name="Newcomers"))
    await channel.send(f"{random.choice(config.greetings)}, {member.mention}\nUse `!verify <osu_username>` to get verified!")


async def return_token():
    '''return temporary token / retrieve new token'''
    global tmp_token
    global date
    url = 'https://osu.ppy.sh/oauth/token'
    data = {'client_id': config.api_id,'client_secret': config.api_token,'grant_type': 'client_credentials','scope': 'public'}
    
    if tmp_token:
        if datetime.now().timestamp() - date >= 86000:
            print("Token older than 30 seconds, retrieving new one")
            tmp_token = requests.post(url, data).json()
            date = datetime.now().timestamp()
            return tmp_token['access_token']
        else:
            print("Using token retrieved earlier")
            return tmp_token['access_token']
    else:
        print("Retrieving new token")
        tmp_token = requests.post(url, data).json()
        date = datetime.now().timestamp()
        return tmp_token['access_token']

### START ARTIST PARSING FUNCTION
async def parse_artists(artist_credit):
    s = ""
    for entry in artist_credit:
        if type(entry) is dict:
            s += f'{entry["artist"]["sort-name"]}'
        else:
            s += entry
    return s
### END ARTIST PARSING FUNCTION

### START ACOUSTIC ANALYSIS FUNCTION
async def get_bpm_key(song_id, e):
    try:
        # Get the data from API
        response = requests.get(f"https://acousticbrainz.org/api/v1/{song_id}/low-level")
        response.raise_for_status()
        json_response = response.json()
        
        # Assign the data to variables
        bpm = round(json_response["rhythm"]["bpm"])
        key = json_response["tonal"]["key_key"]
        scale = json_response["tonal"]["key_scale"]
        key_probability = json_response["tonal"]["key_strength"]
                    
        # Add fields to embed          
        e.add_field(name = "BPM", value = bpm, inline = True)
        e.add_field(name = f"Key signature: {key} {scale}", value = f"Accuracy: {key_probability*100:.2f}%", inline = True)
    except Exception:
        pass
### END ACOUSTIC ANALYSIS FUNCTION
    
### START GET COVER ART FUNCTION
async def get_cover_art(release_id, e):
    
    # Try to get the cover art from CoverArtArchive
    try:
        print("Trying CoverArtArchive")
        redirect=requests.get(mb.get_image_list(release_id)["images"][0]["thumbnails"]["large"]).url
        e.set_thumbnail(url=redirect)
    except Exception:
        
        # Try to get the cover art from Amazon
        try:
            print("Trying Amazon")
            response = requests.get(f'https://musicbrainz.org/ws/2/release/{release_id}?fmt=json')
            response.raise_for_status()
            asin = response.json()["asin"]
            if not asin:
                raise ValueError("ASIN not found")
            e.set_thumbnail(url=f"https://images-na.ssl-images-amazon.com/images/P/{asin}.jpg")
            
        # Else set a dummy image
        except Exception:
            print("Using fallback image")
            e.set_thumbnail(url="https://cdn.discordapp.com/emojis/778698404317364224.png")
### END GET COVER ART FUNCTION

### START USER COMMANDS
### START DL COMMAND
@client.command()
async def dl(ctx, *, input: str):
    ''' Interactive metadata lookup for a song. Usage example: !dl <artist> <title> '''
    
    # Set the musicbrainz agent, and get the recordings
    mb.set_useragent("GraveyardBot", "8.7", "beatmaster@beatconnect.io")
    result = mb.search_recordings(query=" AND ".join(input.split()), limit=5)

    # If song was found
    if result["recording-list"]:
        
        # Loop through all of the songs
        for recording_index, recording in enumerate(result["recording-list"]):
            song = recording['title']
            artists = await parse_artists(recording["artist-credit"])
            print(f"Song #{recording_index+1}: {song}, Artist credit: {artists}")
            print(json.dumps(recording, indent=4)) 
            
            # Loop through all of the albums
            for release_index, release in enumerate(recording["release-list"]):
                album = release["title"]
                print(f'\nAlbum #{release_index+1}, Title: {album}')
                
                # Add embed and embed fields
                e = discord.Embed(title = "Song has been found!", description = f'Song ({recording_index+1}/{str(len(result["recording-list"]))}), Album ({release_index+1}/{str(len(recording["release-list"]))})', color = 0x2ecc71)

                # Retrieve BPM and key
                await get_bpm_key(recording["id"], e)

                # Set main fields
                e.add_field(name = "Song", value = song, inline = False)
                e.add_field(name = "Artist", value = artists, inline = False)
                e.add_field(name = "Album", value = album, inline = False)
                
                # Try to get the cover art
                await get_cover_art(release["id"], e)

                # Check whether to send a new message or edit
                if release_index == 0 and recording_index == 0:
                    message = await ctx.send(embed=e)
                else:
                    await message.edit(embed=e)
                    
                # Assign reactions to message
                emojis = ["⏩","❌"]
                for emoji in emojis:
                    await message.add_reaction(emoji)

                # Function that confirms that the user's reaction is valid and was placed on appropriate message
                def check_reaction(reaction, user):
                    return user != client.user and reaction.message == message and user == ctx.author and reaction.emoji in emojis

                # Wait for user to react
                reaction, user = await client.wait_for("reaction_add", check=check_reaction, timeout=60)
                
                if str(reaction.emoji) == '⏩':
                    await message.remove_reaction('⏩', user)
                    pass
                if str(reaction.emoji) == "❌":
                    await message.delete()
                    await ctx.message.delete()
                    
    # If song was not found
    else:
        e = discord.Embed(title = "Song not found!", color = 0xff3232)
        await ctx.send(embed = e)
### END DL COMMAND
        
@client.command()
async def user(ctx, user_id):
    '''User details. Use: !user <osu_username>'''
    response = requests.get(f'https://osu.ppy.sh/api/v2/users/{user_id}/osu', headers={'Authorization': f'Bearer {await return_token()}' }).json()
    e = discord.Embed(title = f"User Details")
    e.add_field(name = "Username", value = response['username'])
    e.add_field(name = "Online", value = ':green_circle:' if response['is_online'] else ':red_circle:')
    e.add_field(name = "Country", value = response['country']['name'])
    e.add_field(name = "PP", value = response['statistics']['pp'])
    e.add_field(name = "Graveyarded Maps", value = response['graveyard_beatmapset_count'])
    e.add_field(name = "Ranked Maps", value = response['ranked_and_approved_beatmapset_count'])
    e.set_thumbnail(url=response['avatar_url'])
    await ctx.send(embed = e)

@client.command()
async def verify(ctx, user):
    '''Verify an user. Use: !verify <osu_username>'''
    response = requests.get(f'https://osu.ppy.sh/api/v2/users/{user}/osu', headers={'Authorization': f'Bearer {await return_token()}' }).json()
    graved = response['graveyard_beatmapset_count']
    tainted = response['ranked_and_approved_beatmapset_count']

    # perhaps simplify this
    role1 = discord.utils.get(ctx.guild.roles, name="Graveyard Rookie (<5 Maps)")
    role2 = discord.utils.get(ctx.guild.roles, name="Graveyard Amateur (5-15 Maps)")
    role3 = discord.utils.get(ctx.guild.roles, name="Graveyard Adept (15-30 Maps)")
    role4 = discord.utils.get(ctx.guild.roles, name="Graveyard Veteran (30-50 Maps)")
    role5 = discord.utils.get(ctx.guild.roles, name="Graveyard Revenant (50+ Maps)")
    role6 = discord.utils.get(ctx.guild.roles, name="Tainted Mapper")

    if tainted > 0:
        await ctx.author.add_roles(role6)
    elif graved in range(0,5):
        await ctx.author.add_roles(role1)
    elif graved in range(5,15):
        await ctx.author.add_roles(role2)
    elif graved in range(15,30):
        await ctx.author.add_roles(role3)
    elif graved in range(30,50):
        await ctx.author.add_roles(role4)
    elif graved in range(50,666):
        await ctx.author.add_roles(role5)
    await ctx.author.remove_roles(discord.utils.get(ctx.guild.roles, name="Newcomers"))

    e = discord.Embed(title = f"User Verified!")
    e.add_field(name = "Username", value = response['username'], inline=False)
    avatar_url = response['avatar_url']
    if 'avatar-guest' in avatar_url:
        avatar_url = f'https://osu.ppy.sh{avatar_url}'
    e.set_thumbnail(url=avatar_url)
    await ctx.send(embed = e)
### END USER COMMANDS

### START ADMIN COMMANDS
@client.command()
@commands.has_role("Admin")
async def kick(ctx, member:discord.Member):
    ''' Kicks a member. Use: !kick <@user> '''
    await member.kick()
    channel = client.get_channel(config.announce_channel)
    #await channel.send("**User **" +"`"+(member.nick if member.nick else member.name)+"`"+ f"** {random.choice(config.kick_punishment)}** <:tux:775785821768122459>")
    await channel.send(f"**User **`{(member.nick if member.nick else member.name)}` **{random.choice(config.kick_punishment)}** <:tux:775785821768122459>")

@client.command()
@commands.has_role("Admin")
async def ban(ctx, member:discord.Member):
    ''' Bans a member. Use: !ban <@user> '''
    await member.ban()
    channel = client.get_channel(config.announce_channel)
    #await channel.send("**User **" +"`"+(member.nick if member.nick else member.name)+"`"+ f"** {random.choice(config.ban_punishment)}** <:tux:775785821768122459>")
    await channel.send(f"**User **`{(member.nick if member.nick else member.name)}` **{random.choice(config.ban_punishment)}** <:tux:775785821768122459>")
### END ADMIN COMMANDS
    
client.run(config.discord_token)
