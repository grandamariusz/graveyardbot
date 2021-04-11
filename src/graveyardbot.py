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

@client.event
async def on_ready():
    print("I'm ready")
    await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="87th dimension"))

@client.event
async def on_member_join(member):
    channel = client.get_channel(config.join_channel)
    await member.add_roles(discord.utils.get(member.guild.roles, name="Newcomers"))
    await channel.send(f"{random.choice(config.greetings)}, {member.mention}\nUse `!verify <osu_username>` to get verified!")

@client.command()
async def user(ctx, user_id):
    '''User details. Use: !user <osu_username>'''
    response = requests.get('https://osu.ppy.sh/api/v2/users/'+user_id+'/osu', headers={'Authorization': 'Bearer '+ await return_token()}).json()
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
    response = requests.get('https://osu.ppy.sh/api/v2/users/'+user+'/osu', headers={'Authorization': 'Bearer ' + await return_token()}).json()
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
        avatar_url = 'https://osu.ppy.sh' + avatar_url
    e.set_thumbnail(url=avatar_url)
    await ctx.send(embed = e)
    
@client.command(pass_context=True)
async def roll(ctx):
    ''' Roll one of the three goblins. Use: !roll '''
    message = await ctx.send("Rolled")
    emojis = ["✅","❌"]
    for emoji in emojis:
        await message.add_reaction(emoji)
        
    def checkReaction(reaction, user):
        return user != client.user and user == ctx.author and (str(reaction.emoji) == '✅' or str(reaction.emoji) == '❌')
    
    reaction, user = await client.wait_for("reaction_add", check=checkReaction)
    await ctx.send("<:tux:775785821768122459>") if str(reaction.emoji) == '✅' else await ctx.send("Not Pog")

### START DOWNLOAD COMMAND
@client.command()
async def download(ctx, *, input: str):
    ''' Graveyard Gamer Maneuver™ '''
    mb.set_useragent("GraveyardBot", "8.7", "beatmaster@beatconnect.io")
    result = mb.search_recordings(query=" AND ".join(input.split()), limit=5)
    print(json.dumps(result, indent=4))
    if (result["recording-list"]):
        albums = result["recording-list"][0]["release-list"]
        e = discord.Embed(title = "Song has been found!", description = f"Album ({1}/{str(len(albums))})", color = 0x2ecc71)

        for release in result["recording-list"][0]["release-list"]:
            try:
                try:    
                    e.set_thumbnail(url=requests.get(mb.get_release_group_image_list(release["release-group"]["id"])["images"][0]["image"]).url)
                except Exception:
                    e.set_thumbnail(url="https://cdn.discordapp.com/emojis/768194173685071934.png")
                    pass
                e.add_field(name = "Title", value = result["recording-list"][0]["title"], inline = False)
                e.add_field(name = "Artist", value = result["recording-list"][0]["artist-credit"][0]["name"], inline = False)
                e.add_field(name = "Album", value = release["release-group"]["title"], inline = False) 
                break
            except Exception:
                pass
        await ctx.send(embed = e)
    else:
        #await ctx.send("**Song not found!**")
        e = discord.Embed(title = "Song not found", color = 0xff3232)
        await ctx.send(embed = e)
### END DOWNLOAD COMMAND

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

### START REACTION CHECK FUNCTION
async def reaction_check(ctx, message):
    emojis = ["✅","❌"]
    for emoji in emojis:
        await message.add_reaction(emoji)

    def checkReaction(reaction, user):
        return user != client.user and user == ctx.author and (str(reaction.emoji) == '✅' or str(reaction.emoji) == '❌')
    
    reaction, user = await client.wait_for("reaction_add", check=checkReaction)
    
    if str(reaction.emoji) == '✅':
        await ctx.send("<:tux:775785821768122459>")
        return True
    elif str(reaction.emoji) == '❌':
        await ctx.send("Not Pog")
        return False
        
### END REACTION CHECK FUNCTION

### START DL COMMAND
@client.command()
async def dl(ctx, *, input: str):
    ''' Graveyard Gamer Maneuver™ '''
    mb.set_useragent("GraveyardBot", "8.7", "beatmaster@beatconnect.io")
    result = mb.search_recordings(query=" AND ".join(input.split()), limit=5)   
    if result["recording-list"]:
        song_counter = 1
        for recording in result["recording-list"]:
            song = recording['title']
            artists = await parse_artists(recording["artist-credit"])
            print(f"Song: {song}")
            print(f"Artist credit: {artists}")
            print(json.dumps(recording, indent=4))
            
            album_counter = 1
            for release in recording["release-list"]:
                album = release["title"]
                print(f'Album {album_counter} title: {album}')
                e = discord.Embed(title = "Song has been found!", description = f'Song ({song_counter}/{str(len(result["recording-list"]))}), Album ({album_counter}/{str(len(recording["release-list"]))})', color = 0x2ecc71)
                e.add_field(name = "Song", value = song, inline = False)
                e.add_field(name = "Artist", value = artists, inline = False)
                e.add_field(name = "Album", value = album, inline = False)
                
                try:
                    redirect=requests.get(mb.get_image_list(release["id"])["images"][0]["image"]).url
                    print(json.dumps(mb.get_image_list(release["id"]), indent=4))
                    e.set_thumbnail(url=redirect)
                except Exception:
                    try:
                        with urllib.request.urlopen("https://musicbrainz.org/ws/2/release/"+release["id"]+"?fmt=json") as lookup:
                            json_convert = json.loads(lookup.read().decode())
                            print(json.dumps(json_convert, indent=4))
                            asin = json_convert["asin"]
                            print(asin)
                            e.set_thumbnail(url="https://images-na.ssl-images-amazon.com/images/P/"+asin+".jpg")
                    except Exception:
                        e.set_thumbnail(url="https://cdn.discordapp.com/emojis/768194173685071934.png")
                        pass
                    pass
                
                message = await ctx.send(embed = e)
                if (await reaction_check(ctx, message)):
                    print("BREAKING")
                    break
                else:
                    pass
                    print("PASSING")
                album_counter += 1
            else:
                continue
            print("\n")
            song_counter += 1
            break
    else:
        e = discord.Embed(title = "Song not found", color = 0xff3232)
        await ctx.send(embed = e)
### END DL COMMAND

### START ADMIN COMMANDS
@client.command()
@commands.has_role("Admin")
async def kick(ctx, member:discord.Member):
    ''' Kicks a member. Use: !kick <@user> '''
    await member.kick()
    channel = client.get_channel(config.announce_channel)
    await channel.send("**User **" +"`"+(member.nick if member.nick else member.name)+"`"+ f"** {random.choice(config.kick_punishment)}** <:tux:775785821768122459>")

@client.command()
@commands.has_role("Admin")
async def ban(ctx, member:discord.Member):
    ''' Bans a member. Use: !ban <@user> '''
    await member.ban()
    channel = client.get_channel(config.announce_channel)
    await channel.send("**User **" +"`"+(member.nick if member.nick else member.name)+"`"+ f"** {random.choice(config.ban_punishment)}** <:tux:775785821768122459>")
### END ADMIN COMMANDS

'''
albums_iter=iter(albums)
while (True) :           
next_val = next(albums_iter,'end') 
# if there are no more values in iterator, break the loop
if next_val == 'end': 
break
else :
print ("\nNext Val: ") 
print (json.dumps(next_val, indent=4))
'''

client.run(config.discord_token)
