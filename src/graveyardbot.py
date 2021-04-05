import discord, os, urllib.request, json, random, asyncio, requests, re
from discord.ext import tasks, commands
from osuapi import OsuApi, ReqConnector
import config
import datetime

intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix=config.prefix, intents=intents)

# TODO: persist token
token_cache = {
    "token": "dummy",
    "expiry_date": datetime.datetime(1,1,1)
}

### Helper functions

def getToken():
    now = datetime.datetime.today()
    if token_cache["expiry_date"] <= now:
        url = "https://osu.ppy.sh/oauth/token"
        data = {"client_id": config.api_id,
                "client_secret": config.api_token,
                "grant_type": "client_credentials",
                "scope": "public"}
        token = requests.post(url, data).json()
        token_cache["token"] = token["access_token"]
        token_cache["expiry_date"] = now + datetime.timedelta(seconds=token["expires_in"])
    return token_cache["token"]
        
def getUser(user_id):
    token = getToken()

    user = "https://osu.ppy.sh/api/v2/users/"+user_id+"/osu"
    b = "Bearer "+token
    return requests.get(user, headers={"Authorization": b}).json()

### Event functions

@client.event
async def on_ready():
    print("I'm ready")
    await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="87th dimension"))

@client.event
async def on_member_join(member):
    role = discord.utils.get(member.guild.roles, name="Newcomers")
    channel = client.get_channel(config.join_channel)
    await member.add_roles(role)

    g = ['Welcome to hell', 'Abandon all hope, ye who enter here','The path to paradise, begins in hell', 'Heaven might shine bright, but so do flames']
    await channel.send(f"{random.choice(g)}, {member.mention}\nUse `!verify <link-to-your-osu-profile>` to get verified!")

@client.command()
async def channel(ctx):
    '''Shows the ID of channel in which this command was used'''
    await ctx.send("Channel ID: "+str(ctx.message.channel.id))

@client.command()
async def user(ctx, user_id):
    '''User details. Use: !user <user_id>'''

    response = getUser(user_id);

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
async def verify(ctx, link):
    '''Verify a user. Use: !verify <link_to_your_osu_profile>'''
    regex = re.search(r"(?P<id>\d+)", link)
    user_id = regex.group("id")

    response = getUser(user_id);

    graved = response['graveyard_beatmapset_count']
    tainted = response['ranked_and_approved_beatmapset_count']

    roles = [
        { "name": "Graveyard Rookie (<5 Maps)", "condition": lambda x : x >= 0 or x < 5 },
        { "name": "Graveyard Amateur (5-15 Maps)", "condition": lambda x : x >= 5 or x < 15 },
        { "name": "Graveyard Adept (15-30 Maps)", "condition": lambda x : x >= 15 or x < 30 },
        { "name": "Graveyard Veteran (30-50 Maps)", "condition": lambda x : x >= 30 or x < 50 },
        { "name": "Graveyard Revenant (50+ Maps)", "condition": lambda x : x >= 50 }
    ]
    
    if tainted > 0:
        role = discord.utils.get(ctx.guild.roles, name="Tainted Mapper")
        await ctx.author.add_roles(role)
    else:
        for r in roles:
            if r["condition"](graved):
                role = discord.utils.get(ctx.guild.roles, name=r["name"])
                await ctx.author.add_roles(role)
                break

    e = discord.Embed(title = f"User Verified!")
    e.add_field(name = "Username", value = response['username'], inline=False)
    avatar_url = response['avatar_url']
    if 'avatar-guest' in avatar_url:
        avatar_url = 'https://osu.ppy.sh' + avatar_url
    e.set_thumbnail(url=avatar_url)
    await ctx.send(embed = e)

@client.command()
async def roll(ctx):
    ''' Roll one of the three goblins. Use: !roll '''
    await ctx.send("You've rolled: "+random.choice([':japanese_goblin:', '<:ungoblin:777794404106502154>', '<:overgoblin:780773006829551617>']))

@client.command()
async def test(ctx):
    ''' Test '''
    await ctx.send("Absolute state of Linux <:tux:775785821768122459>")

client.run(config.discord_token)
