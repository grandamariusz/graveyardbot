import discord, os, urllib.request, json, random, asyncio, requests, re
from discord.ext import tasks, commands
from osuapi import OsuApi, ReqConnector
import config

intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix=config.prefix, intents=intents)

###################################### Event functions
@client.event
async def on_ready():
    print("I'm ready")
    await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="87th dimension"))

@client.event
async def on_member_join(member):
    role = discord.utils.get(member.guild.roles, name="Newcomers")
    channel = client.get_channel(config.join_channel)
    await member.add_roles(role)

    g = ['Welcome to hell', 'Abandon all hope, ye who enter here','The path to paradise, begins in hell', 'Heaven may shine bright, but so do flames']
    await channel.send(f"{random.choice(g)}, {member.mention}\nUse `!verify <link-to-your-osu-profile>` to get verified!")

@client.command()
async def channel(ctx):
    '''Shows the ID of channel in which this command was used'''
    await ctx.send("Channel ID: "+str(ctx.message.channel.id))

@client.command()
async def user(ctx, user_id):
    '''User details. Use: !user <user_id>'''

    url = 'https://osu.ppy.sh/oauth/token'
    data = {'client_id': config.api_id,
            'client_secret': config.api_token,
            'grant_type': 'client_credentials',
            'scope': 'public'}
    token = requests.post(url, data).json()

    user = 'https://osu.ppy.sh/api/v2/users/'+user_id+'/osu'
    b = 'Bearer '+ token['access_token']
    response = requests.get(user, headers={'Authorization': b}).json()

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
    '''Verify an user. Use: !verify <link_to_your_osu_profile>'''
    regex = re.search(r'(?P<id>\d+)', link)
    user_id = regex.group('id')

    # split this into another function
    url = 'https://osu.ppy.sh/oauth/token'
    data = {'client_id': config.api_id,
            'client_secret': config.api_token,
            'grant_type': 'client_credentials',
            'scope': 'public'}
    token = requests.post(url, data).json()

    user = 'https://osu.ppy.sh/api/v2/users/'+user_id+'/osu'
    b = 'Bearer '+token['access_token']
    response = requests.get(user, headers={'Authorization': b}).json()
    graved = response['graveyard_beatmapset_count']
    tainted = response['ranked_and_approved_beatmapset_count']

    # perhaps simplify this
    role0 = discord.utils.get(ctx.guild.roles, name="Newcomers")
    role1 = discord.utils.get(ctx.guild.roles, name="Graveyard Rookie (<5 Maps)")
    role2 = discord.utils.get(ctx.guild.roles, name="Graveyard Amateur (5-15 Maps)")
    role3 = discord.utils.get(ctx.guild.roles, name="Graveyard Adept (15-30 Maps)")
    role4 = discord.utils.get(ctx.guild.roles, name="Graveyard Veteran (30-50 Maps)")
    role5 = discord.utils.get(ctx.guild.roles, name="Graveyard Revenant (50+ Maps)")
    role6 = discord.utils.get(ctx.guild.roles, name="Tainted Mapper")

    print(ctx.author.roles)
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

    await ctx.author.remove_roles(role0)

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

### START DOWNLOAD FUNCTION
@client.command()
async def download(ctx, song):
    ''' Graveyard Gamer Maneuver™ '''
    await ctx.send(song)
### END DOWNLOAD FUNCTION

client.run(config.discord_token)
