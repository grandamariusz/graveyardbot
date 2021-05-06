import discord, os, urllib.request, json, random, asyncio, requests, re, config, math, time
from discord.ext import tasks, commands
from osuapi import OsuApi, ReqConnector
from database import Database
from datetime import datetime, timedelta
import musicbrainzngs as mb

intents = discord.Intents.default()
intents.members = True
intents.reactions = True
client = commands.Bot(command_prefix=config.prefix, intents=intents)

# Create and setup database with a "tokens" table
# Basic idea is that we store them like this
# +---------+---------------+--------------+
# | name    | value         | expiry_date  |
# +---------+---------------+--------------+
# | osu_api | <the_token>   | <time_stamp> |
# | ripple  | <another_one> | <time_stamp> |
# | etc..   | <more_stuff>  | <time_stamp> |
# +---------+---------------+--------------+
db = Database("secrets.db")
db.execute("create table if not exists tokens (name text unique, value text, expiry_date text default \"0001-01-01 00:00:00.000000\")")

emotes = config.emotes

watchathon_msg = ""

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
    now = datetime.today()

    # Get token from database
    ret = db.tokens["osu_api"]
    # If there is no token, the expiry will be set to the minimum time possible
    expiry_date = ret and ret.expiry_date or str(datetime.min)

    # If the token has expired, get a new one
    if datetime.fromisoformat(expiry_date) <= now:
        print("Old osu!api auth token has expired, retreiving new one")
        url = "https://osu.ppy.sh/oauth/token"
        data = {"client_id": config.api_id,
                "client_secret": config.api_token,
                "grant_type": "client_credentials",
                "scope": "public"}
        token = requests.post(url, data).json()

        # Store new token and expiry date in database
        db.tokens["osu_api"] = {
            "value": token["access_token"],
            "expiry_date": str(now + timedelta(seconds=token["expires_in"]))
        }
    else:
        print("Reusing existing osu!api auth token")
    return db.tokens["osu_api"].value

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

            if asin:
                response = requests.get(f"https://images-na.ssl-images-amazon.com/images/P/{asin}.jpg")
                if response.headers['Content-Type'] == "image/gif":
                    raise ValueError("Image is a 1x1 GIF")
                else:
                    e.set_thumbnail(url=f"https://images-na.ssl-images-amazon.com/images/P/{asin}.jpg")
            else:
                raise ValueError("ASIN not found")

        # Else set a dummy image
        except Exception:
            print("Using fallback image")
            e.set_thumbnail(url="https://cdn.discordapp.com/emojis/778698404317364224.png")
### END GET COVER ART FUNCTION

### START REACTIONS FUNCTION
async def wait_for_reaction(ctx, message, e, emojis):

    for emoji in emojis:
        await message.add_reaction(emoji)

    def check_reaction(reaction, user):
        return user != client.user and reaction.message == message and user == ctx.author and str(reaction.emoji) in emojis

    # Wait for user to react
    try:
        reaction, user = await client.wait_for("reaction_add", check=check_reaction, timeout=60)
    except Exception as error:
        print(error)
        print("Operation timed out!")
        await message.clear_reactions()
        e.color = 0xe3e6df
        await message.edit(embed=e)
        return None, None
    return reaction, user
### END REACTIONS FUNCTION

### START USER COMMANDS
### START DL COMMAND
@client.command()
async def dl(ctx, *, input: str):
    ''' Interactive metadata lookup for a song. Usage example: !dl <artist> <title> '''
    
    # Set the musicbrainz agent and get the recordings
    mb.set_useragent("GraveyardBot", "8.7", "beatmaster@beatconnect.io")
    result = mb.search_recordings(query=" AND ".join(input.split()), limit=5)

    # If song was found
    if "recording-list" in result:
        
        # Loop through all of the songs
        exit_flag = reset_flag = edit_flag = False
        while not (exit_flag and reset_flag):
            reset_flag = False
            for recording_index, recording in enumerate(result["recording-list"]):
                song = recording['title']
                artists = await parse_artists(recording["artist-credit"])
                print(f"Song #{recording_index+1}: {song}, Artist credit: {artists}")

                if "release-list" in recording:
                    # Loop through all of the albums
                    for release_index, release in enumerate(recording["release-list"]):
                        album = release["title"]
                        print(f'\nAlbum #{release_index+1}, Title: {album}')

                        # Add embed and embed fields
                        e = discord.Embed(title = "Song has been found!", color = 0x2ecc71)

                        # Retrieve BPM and key
                        await get_bpm_key(recording["id"], e)

                        # Set main fields
                        e.add_field(name = f'Song ({recording_index+1}/{str(len(result["recording-list"]))})', value = song, inline = False)
                        e.add_field(name = f'Album ({release_index+1}/{str(len(recording["release-list"]))})', value = album, inline = False)
                        e.add_field(name = "Artist", value = artists, inline = False)

                        # Try to get the cover art
                        await get_cover_art(release["id"], e)

                        # Check whether to send a new message or edit
                        if release_index == 0 and recording_index == 0 and not edit_flag:
                            message = await ctx.send(embed=e)
                        else:
                            await message.edit(embed=e)

                        # Determine which emojis to add
                        await message.clear_reactions()
                        emojis = ["✅"]
                        if release_index + 1 < len(recording["release-list"]):
                            emojis.append("⏩")
                        if recording_index + 1 < len(result["recording-list"]):
                            emojis.append("⏭")
                        emojis.append("↩️")
                        emojis.append("🛑")

                        # Add emojis and listen for reaction
                        reaction, user = await wait_for_reaction(ctx, message, e, emojis)

                        # Perform appropriate operation upon reaction
                        if reaction is None:
                            exit_flag = reset_flag = True
                            break
                        if str(reaction.emoji) == '✅':
                            exit_flag = reset_flag = True
                            await message.clear_reactions()
                            await ctx.send("Song accepted.")
                        if str(reaction.emoji) == '⏩':
                            await message.remove_reaction('⏩', user)
                            await message.edit(embed=discord.Embed(title = "🔄 Loading next album...", color = 0x3b88c3))
                        if str(reaction.emoji) == '⏭':
                            await message.remove_reaction('⏭', user)
                            await message.edit(embed=discord.Embed(title = "🔄 Loading next song...", color = 0x3b88c3))
                            break
                        if str(reaction.emoji) == "↩️":
                            reset_flag = edit_flag = True
                            await message.clear_reactions()
                            break
                        if str(reaction.emoji) == "🛑":
                            exit_flag = reset_flag = True
                            await message.clear_reactions()
                            await message.edit(embed=discord.Embed(title = "⚠️ Operation cancelled!", color = 0xffcc4d))

                        if exit_flag:
                            # Exit release loop
                            break

                    if exit_flag or reset_flag:
                        # Exit recording loop
                        break

                # If no release was found
                else:
                    # Add embed and embed fields
                    e = discord.Embed(title = "Song has been found!", color = 0x2ecc71)

                    # Retrieve BPM and key
                    await get_bpm_key(recording["id"], e)

                    # Set main fields
                    e.add_field(name = f'Song ({recording_index+1}/{str(len(result["recording-list"]))})', value = song, inline = False)
                    e.add_field(name = "Artist", value = artists, inline = False)

                    # Set dummy cover art
                    e.set_thumbnail(url="https://cdn.discordapp.com/emojis/778698404317364224.png")
                    await ctx.send(embed = e)
                
    # If song was not found
    else:
        e = discord.Embed(title = "Song not found!", color = 0xff3232)
        await ctx.send(embed = e)
### END DL COMMAND

countries = {
    "Anonymous Proxy": "?",
    "Satellite Provider": "?",
    "Andorra": ":flag_ad:",
    "United Arab Emirates": ":flag_ae:",
    "Afghanistan": ":flag_af:",
    "Antigua and Barbuda": ":flag_ag:",
    "Anguilla": ":flag_ai:",
    "Albania": ":flag_al:",
    "Armenia": ":flag_am:",
    "Netherlands Antilles": ":flag_an:",
    "Angola": ":flag_ao:",
    "Asia/Pacific Region": ":flag_ap:",
    "Antarctica": ":flag_aq:",
    "Argentina": ":flag_ar:",
    "American Samoa": ":flag_as:",
    "Austria": ":flag_at:",
    "Australia": ":flag_au:",
    "Aruba": ":flag_aw:",
    "Aland Islands": ":flag_ax:",
    "Azerbaijan": ":flag_az:",
    "Bosnia and Herzegovina": ":flag_ba:",
    "Barbados": ":flag_bb:",
    "Bangladesh": ":flag_bd:",
    "Belgium": ":flag_be:",
    "Burkina Faso": ":flag_bf:",
    "Bulgaria": ":flag_bg:",
    "Bahrain": ":flag_bh:",
    "Burundi": ":flag_bi:",
    "Benin": ":flag_bj:",
    "Saint Barthelemy": ":flag_bl:",
    "Bermuda": ":flag_bm:",
    "Brunei": ":flag_bn:",
    "Bolivia": ":flag_bo:",
    "Brazil": ":flag_br:",
    "Bahamas": ":flag_bs:",
    "Bhutan": ":flag_bt:",
    "Bouvet Island": ":flag_bv:",
    "Botswana": ":flag_bw:",
    "Belarus": ":flag_by:",
    "Belize": ":flag_bz:",
    "Canada": ":flag_ca:",
    "Cocos (Keeling) Islands": ":flag_cc:",
    "Congo: The Democratic Republic of the": ":flag_cd:",
    "Central African Republic": ":flag_cf:",
    "Congo": ":flag_cg:",
    "Switzerland": ":flag_ch:",
    "Cote D\"Ivoire": ":flag_ci:",
    "Cook Islands": ":flag_ck:",
    "Chile": ":flag_cl:",
    "Cameroon": ":flag_cm:",
    "China": ":flag_cn:",
    "Colombia": ":flag_co:",
    "Costa Rica": ":flag_cr:",
    "Cuba": ":flag_cu:",
    "Cabo Verde": ":flag_cv:",
    "Christmas Island": ":flag_cx:",
    "Cyprus": ":flag_cy:",
    "Czech Republic": ":flag_cz:",
    "Germany": ":flag_de:",
    "Djibouti": ":flag_dj:",
    "Denmark": ":flag_dk:",
    "Dominica": ":flag_dm:",
    "Dominican Republic": ":flag_do:",
    "Algeria": ":flag_dz:",
    "Ecuador": ":flag_ec:",
    "Estonia": ":flag_ee:",
    "Egypt": ":flag_eg:",
    "Western Sahara": ":flag_eh:",
    "Eritrea": ":flag_er:",
    "Spain": ":flag_es:",
    "Ethiopia": ":flag_et:",
    "Europe": ":flag_eu:",
    "Finland": ":flag_fi:",
    "Fiji": ":flag_fj:",
    "Falkland Islands (Malvinas)": ":flag_fk:",
    "Micronesia: Federated States of": ":flag_fm:",
    "Faroe Islands": ":flag_fo:",
    "France": ":flag_fr:",
    "France: Metropolitan": ":flag_fx:",
    "Gabon": ":flag_ga:",
    "United Kingdom": ":flag_gb:",
    "Grenada": ":flag_gd:",
    "Georgia": ":flag_ge:",
    "French Guiana": ":flag_gf:",
    "Guernsey": ":flag_gg:",
    "Ghana": ":flag_gh:",
    "Gibraltar": ":flag_gi:",
    "Greenland": ":flag_gl:",
    "Gambia": ":flag_gm:",
    "Guinea": ":flag_gn:",
    "Guadeloupe": ":flag_gp:",
    "Equatorial Guinea": ":flag_gq:",
    "Greece": ":flag_gr:",
    "South Georgia and the South Sandwich Islands": ":flag_gs:",
    "Guatemala": ":flag_gt:",
    "Guam": ":flag_gu:",
    "Guinea-Bissau": ":flag_gw:",
    "Guyana": ":flag_gy:",
    "Hong Kong": ":flag_hk:",
    "Heard Island and McDonald Islands": ":flag_hm:",
    "Honduras": ":flag_hn:",
    "Croatia": ":flag_hr:",
    "Haiti": ":flag_ht:",
    "Hungary": ":flag_hu:",
    "Indonesia": ":flag_id:",
    "Ireland": ":flag_ie:",
    "Israel": ":flag_il:",
    "Isle of Man": ":flag_im:",
    "India": ":flag_in:",
    "British Indian Ocean Territory": ":flag_io:",
    "Iraq": ":flag_iq:",
    "Iran: Islamic Republic of": ":flag_ir:",
    "Iceland": ":flag_is:",
    "Italy": ":flag_it:",
    "Jersey": ":flag_je:",
    "Jamaica": ":flag_jm:",
    "Jordan": ":flag_jo:",
    "Japan": ":flag_jp:",
    "Kenya": ":flag_ke:",
    "Kyrgyzstan": ":flag_kg:",
    "Cambodia": ":flag_kh:",
    "Kiribati": ":flag_ki:",
    "Comoros": ":flag_km:",
    "Saint Kitts and Nevis": ":flag_kn:",
    "Korea: Democratic People\"s Republic of": ":flag_kp:",
    "South Korea": ":flag_kr:",
    "Kuwait": ":flag_kw:",
    "Cayman Islands": ":flag_ky:",
    "Kazakhstan": ":flag_kz:",
    "Lao People\"s Democratic Republic": ":flag_la:",
    "Lebanon": ":flag_lb:",
    "Saint Lucia": ":flag_lc:",
    "Liechtenstein": ":flag_li:",
    "Sri Lanka": ":flag_lk:",
    "Liberia": ":flag_lr:",
    "Lesotho": ":flag_ls:",
    "Lithuania": ":flag_lt:",
    "Luxembourg": ":flag_lu:",
    "Latvia": ":flag_lv:",
    "Libya": ":flag_ly:",
    "Morocco": ":flag_ma:",
    "Monaco": ":flag_mc:",
    "Moldova": ":flag_md:",
    "Montenegro": ":flag_me:",
    "Saint Martin": ":flag_mf:",
    "Madagascar": ":flag_mg:",
    "Marshall Islands": ":flag_mh:",
    "North Macedonia": ":flag_mk:",
    "Mali": ":flag_ml:",
    "Myanmar": ":flag_mm:",
    "Mongolia": ":flag_mn:",
    "Macau": ":flag_mo:",
    "Northern Mariana Islands": ":flag_mp:",
    "Martinique": ":flag_mq:",
    "Mauritania": ":flag_mr:",
    "Montserrat": ":flag_ms:",
    "Malta": ":flag_mt:",
    "Mauritius": ":flag_mu:",
    "Maldives": ":flag_mv:",
    "Malawi": ":flag_mw:",
    "Mexico": ":flag_mx:",
    "Malaysia": ":flag_my:",
    "Mozambique": ":flag_mz:",
    "Namibia": ":flag_na:",
    "New Caledonia": ":flag_nc:",
    "Niger": ":flag_ne:",
    "Norfolk Island": ":flag_nf:",
    "Nigeria": ":flag_ng:",
    "Nicaragua": ":flag_ni:",
    "Netherlands": ":flag_nl:",
    "Norway": ":flag_no:",
    "Nepal": ":flag_np:",
    "Nauru": ":flag_nr:",
    "Niue": ":flag_nu:",
    "New Zealand": ":flag_nz:",
    "Other": ":flag_o1:",
    "Oman": ":flag_om:",
    "Panama": ":flag_pa:",
    "Peru": ":flag_pe:",
    "French Polynesia": ":flag_pf:",
    "Papua New Guinea": ":flag_pg:",
    "Philippines": ":flag_ph:",
    "Pakistan": ":flag_pk:",
    "Poland": ":flag_pl:",
    "Saint Pierre and Miquelon": ":flag_pm:",
    "Pitcairn": ":flag_pn:",
    "Puerto Rico": ":flag_pr:",
    "Palestine: State of": ":flag_ps:",
    "Portugal": ":flag_pt:",
    "Palau": ":flag_pw:",
    "Paraguay": ":flag_py:",
    "Qatar": ":flag_qa:",
    "Reunion": ":flag_re:",
    "Romania": ":flag_ro:",
    "Serbia": ":flag_rs:",
    "Russian Federation": ":flag_ru:",
    "Rwanda": ":flag_rw:",
    "Saudi Arabia": ":flag_sa:",
    "Solomon Islands": ":flag_sb:",
    "Seychelles": ":flag_sc:",
    "Sudan": ":flag_sd:",
    "Sweden": ":flag_se:",
    "Singapore": ":flag_sg:",
    "Saint Helena": ":flag_sh:",
    "Slovenia": ":flag_si:",
    "Svalbard and Jan Mayen": ":flag_sj:",
    "Slovakia": ":flag_sk:",
    "Sierra Leone": ":flag_sl:",
    "San Marino": ":flag_sm:",
    "Senegal": ":flag_sn:",
    "Somalia": ":flag_so:",
    "Suriname": ":flag_sr:",
    "Sao Tome and Principe": ":flag_st:",
    "El Salvador": ":flag_sv:",
    "Syrian Arab Republic": ":flag_sy:",
    "Eswatini": ":flag_sz:",
    "Turks and Caicos Islands": ":flag_tc:",
    "Chad": ":flag_td:",
    "French Southern Territories": ":flag_tf:",
    "Togo": ":flag_tg:",
    "Thailand": ":flag_th:",
    "Tajikistan": ":flag_tj:",
    "Tokelau": ":flag_tk:",
    "Timor-Leste": ":flag_tl:",
    "Turkmenistan": ":flag_tm:",
    "Tunisia": ":flag_tn:",
    "Tonga": ":flag_to:",
    "Turkey": ":flag_tr:",
    "Trinidad and Tobago": ":flag_tt:",
    "Tuvalu": ":flag_tv:",
    "Taiwan": ":flag_tw:",
    "Tanzania: United Republic of": ":flag_tz:",
    "Ukraine": ":flag_ua:",
    "Uganda": ":flag_ug:",
    "United States Minor Outlying Islands": ":flag_um:",
    "United States": ":flag_us:",
    "Uruguay": ":flag_uy:",
    "Uzbekistan": ":flag_uz:",
    "Holy See (Vatican City State)": ":flag_va:",
    "Saint Vincent and the Grenadines": ":flag_vc:",
    "Venezuela": ":flag_ve:",
    "Virgin Islands: British": ":flag_vg:",
    "Virgin Islands: U.S.": ":flag_vi:",
    "Vietnam": ":flag_vn:",
    "Vanuatu": ":flag_vu:",
    "Wallis and Futuna": ":flag_wf:",
    "Samoa": ":flag_ws:",
    "Yemen": ":flag_ye:",
    "Mayotte": ":flag_yt:",
    "South Africa": ":flag_za:",
    "Zambia": ":flag_zm:",
    "Zimbabwe": ":flag_zw:"
}

def user_card(response, title = "User details"):
        e = discord.Embed(title = title)
        e.add_field(name = "Username", value = response['username'])
        e.add_field(name = "Online", value = ':green_circle:' if response['is_online'] else ':red_circle:')
        e.add_field(name = "Country", value = countries[response['country']['name']])
        e.add_field(name = "PP", value = str(round(float(response['statistics']['pp']))))
        e.add_field(name = "Graveyarded Maps", value = response['graveyard_beatmapset_count'])
        e.add_field(name = "Ranked Maps", value = response['ranked_and_approved_beatmapset_count'])
        e.add_field(name = "Play Time", value = f"{int(response['statistics']['play_time']) // 3600}h")
        global_rank = response["statistics"]["global_rank"]
        e.add_field(name="Rank", value = f"{'#' + str(global_rank) if global_rank is not None else '-'}")
        avatar_url = response['avatar_url']
        if 'avatar-guest' in avatar_url:
            avatar_url = f'https://osu.ppy.sh{avatar_url}'
        e.set_thumbnail(url=avatar_url)
        return e

@client.command()
async def user(ctx, user_id):
    '''User details. Use: !user <osu_username>'''
    try:
        response = requests.get(f'https://osu.ppy.sh/api/v2/users/{user_id}/osu', headers={'Authorization': f'Bearer {await return_token()}' }).json()
        e = user_card(response)
        await ctx.send(embed = e)
    except Exception:
        await ctx.send("User not found.")

@client.command()
async def verify(ctx, user):
    '''Verify an user. Use: !verify <osu_username>'''
    response = requests.get(f'https://osu.ppy.sh/api/v2/users/{user}/osu', headers={'Authorization': f'Bearer {await return_token()}' }).json()
    graved = response['graveyard_beatmapset_count']
    tainted = response['ranked_and_approved_beatmapset_count']

    roles = [
        "Graveyard Rookie (<5 Maps)",
        "Graveyard Amateur (5-15 Maps)",
        "Graveyard Adept (15-30 Maps)",
        "Graveyard Veteran (30-50 Maps)",
        "Graveyard Revenant (50+ Maps)"
    ]

    if tainted > 0:
        role = discord.utils.get(ctx.guild.roles, name="Tainted Mapper")
        await ctx.author.add_roles(role)
    else:
        for index, requirement in enumerate([5, 15, 30, 50, float("inf")]):
            if graved < requirement:
                role = discord.utils.get(ctx.guild.roles, name=roles[index])
                await ctx.author.add_roles(role)
                break
    await ctx.author.remove_roles(discord.utils.get(ctx.guild.roles, name="Newcomers"))

    e = user_card(response, title = "User verified!")
    await ctx.send(embed = e)

def main_menu(response):
    # Assign beatmap counts and spacers
    counts = [
        response['ranked_and_approved_beatmapset_count'],
        response['loved_beatmapset_count'],
        response['unranked_beatmapset_count'],
        response['graveyard_beatmapset_count']
    ]

    titles = [
        f"{emotes['taint']} ⎯⎯⎯⎯⎯⎯⎯⎯  Tainted  ⎯⎯⎯⎯⎯⎯⎯⎯ {emotes['taint']}",
        f"{emotes['loved']} ⎯⎯⎯⎯⎯⎯⎯⎯⎯  Loved  ⎯⎯⎯⎯⎯⎯⎯⎯⎯ {emotes['loved']}",
        f"{emotes['untaint']} ⎯⎯⎯⎯⎯⎯⎯⎯  Pending  ⎯⎯⎯⎯⎯⎯⎯⎯ {emotes['untaint']}",
        f"{emotes['grave']} ⎯⎯⎯⎯⎯⎯⎯  Graveyard  ⎯⎯⎯⎯⎯⎯⎯ {emotes['grave']}"
    ]

    def embellish(number, embellishment):
        spacer = " "
        if number < 10:
            spacer += " "
        if number > 99:
            spacer = ""
        for digit in str(number):
            if digit == "1":
                spacer += "  "
            return f"⎹ {embellishment} ⌠{spacer}{number}{spacer}⌡ {embellishment} ⎸"

    # Add category fields with their beatmap counts and apply length adjustments respectively
    e = discord.Embed(title=f"{response['username']}'s Map List")
    for i in range(4):
        embellishment = embellish(counts[i], "⎼⎻⎺⎻⎼⎽⎼⎻⎺⎻⎼" if i % 2 == 0 else "⎻⎼⎽⎼⎻⎺⎻⎼⎽⎼⎻")
        e.add_field(name=titles[i], value=embellishment, inline=False)
    e.set_thumbnail(url=response['avatar_url'])
    return e

async def sub_menu(ctx, submenu_title, submenu_color, beatmap_status, beatmap_count, response, message, exit_flag):
    osu_user_id = response['id']

    # Clear reactions from previous menu
    await message.clear_reactions()

    # Iterates over a user's beatmaps in groups of 5
    page = 0
    limit = 5
    page_total = math.ceil(beatmap_count / limit) or 1
    while True:
        # Grab 5 maps from user sorted by latest updated
        if beatmap_count > 0:
            beatmap_list = requests.get(f'https://osu.ppy.sh/api/v2/users/{osu_user_id}/beatmapsets/{beatmap_status}?limit={limit}&offset={page * limit}', headers={'Authorization': f'Bearer {await return_token()}'}).json()
        else:
            # prevent unnecessary request
            beatmap_list = []

        # Create and populate embed with beatmaps
        e = discord.Embed(title=submenu_title, color=submenu_color)
        e.set_thumbnail(url=response['avatar_url'])
        e.set_footer(text=f"Page {page + 1}/{page_total}")
        for beatmap in beatmap_list:
            map_name = f'{beatmap["artist"]} - {beatmap["title_unicode"]}'
            map_link = f'https://osu.ppy.sh/s/{beatmap["id"]}'
            e.add_field(name=map_name, value=map_link, inline=False)
        await message.edit(embed=e)

        # Add emojis and listen for reaction
        emojis = ["⏪", "⏩", "↩️"]
        reaction, user = await wait_for_reaction(ctx, message, e, emojis)

        # Perform appropriate operation upon reaction
        if reaction is None:
            exit_flag = True
            return exit_flag
        if str(reaction.emoji) == '⏪':
            await message.remove_reaction('⏪', user)
            if page == 0:
                page = page_total - 1
            elif page > 0:
                page -= 1
        if str(reaction.emoji) == '⏩':
            await message.remove_reaction('⏩', user)
            if page + 1 == page_total:
                page = 0
            elif page + 1 < page_total:
                page += 1
        if str(reaction.emoji) == '↩️':
            await message.clear_reactions()
            break

### START MAPS COMMAND
@client.command()
async def maps(ctx, osu_user):
    '''Fetches all maps from a user and filters them into beatmap status'''

    # Get osu user data
    response = requests.get(f'https://osu.ppy.sh/api/v2/users/{osu_user}/osu', headers={'Authorization': f'Bearer {await return_token()}'}).json()

    # Main Menu
    edit = False
    exit_flag = False
    while not exit_flag:
        # Construct main menu embed
        e = main_menu(response)

        # Check whether to send a new message or edit
        if not edit:
            message = await ctx.send(embed=e)
        else:
            await message.edit(embed=e)

        # Add emojis and listen for reaction
        emojis = [emotes['taint'], emotes['loved'], emotes['untaint'], emotes['grave']]
        reaction, user = await wait_for_reaction(ctx, message, e, emojis)

        # Perform appropriate operation upon reaction
        if reaction is None:
            break
        if str(reaction.emoji) == emotes['taint']:
            print("Ranked maps")
            await sub_menu(ctx, f"{response['username']}'s tainted maps", 0x4a412a, "ranked_and_approved", response['ranked_and_approved_beatmapset_count'], response, message, exit_flag)
        if str(reaction.emoji) == emotes['loved']:
            await sub_menu(ctx, f"{response['username']}'s loved maps", 0xff66aa, "loved", response['loved_beatmapset_count'], response, message, exit_flag)
        if str(reaction.emoji) == emotes['untaint']:
            await sub_menu(ctx, f"{response['username']}'s pending maps", 0xcca633, "unranked", response['unranked_beatmapset_count'], response, message, exit_flag)
        if str(reaction.emoji) == emotes['grave']:
            exit_flag = await sub_menu(ctx, f"{response['username']}'s graveyarded maps", 0x171a1c, "graveyard", response['graveyard_beatmapset_count'], response, message, exit_flag)
        edit = True
### END MAPS COMMAND
### START BPM COMMAND
@client.command()
async def bpm(ctx, bpm):
    e = discord.Embed(title="BPM calculator and beatsnap divisor assistant", description=f"Input BPM: {bpm}", color=0x3b88c3)
    bpm = int(bpm)
    mspb = 1 / bpm * 60000
    for i in [2, 3, 4, 5, 6, 7, 8, 9, 12, 16]:
        e.add_field(name=f"1/{i} ： ⌠ `{bpm/4*i} bpm` ⌡", value=f"{round(mspb/i,1)}ms between notes", inline=True)
    await ctx.send(embed = e)
### END BPM COMMAND
### END USER COMMANDS

### START ADMIN COMMANDS
@client.command()
@commands.has_role("Admin")
async def kick(ctx, member:discord.Member):
    ''' Kicks a member. Use: !kick <@user> '''
    await member.kick()
    channel = client.get_channel(config.announce_channel)
    #await channel.send("**User **" +"`"+(member.nick if member.nick else member.name)+"`"+ f"** {random.choice(config.kick_punishment)}** {emotes['tux']}")
    await channel.send(f"**User **`{(member.nick if member.nick else member.name)}` **{random.choice(config.kick_punishment)}** {emotes['tux']}")

@client.command()
@commands.has_role("Admin")
async def ban(ctx, member:discord.Member):
    ''' Bans a member. Use: !ban <@user> '''
    await member.ban()
    channel = client.get_channel(config.announce_channel)
    #await channel.send("**User **" +"`"+(member.nick if member.nick else member.name)+"`"+ f"** {random.choice(config.ban_punishment)}** {emotes['tux']}")
    await channel.send(f"**User **`{(member.nick if member.nick else member.name)}` **{random.choice(config.ban_punishment)}** {emotes['tux']}")

@client.command()
@commands.has_role("Admin")
async def silence(ctx, member:discord.Member, duration):
    ''' Silences a member. Use: !silence <@user> <duration-in-seconds>'''
    try:
        duration = abs(int(duration))
        print(duration)
        await ctx.send(f"Silenced {member.name} for {duration} seconds!")
        await member.add_roles(discord.utils.get(ctx.guild.roles, name="Silenced"))
        time.sleep(duration)
        await member.remove_roles(discord.utils.get(ctx.guild.roles, name="Silenced"))
        await ctx.send(f"{duration} seconds have elapsed. Unsilenced {member.name}")
    except ValueError:
        await ctx.send("Duration must be a positive integer.")
### END ADMIN COMMANDS

@client.event
async def on_reaction_add(reaction, user):
    # Bot channel
    channel = client.get_channel(config.announce_channel)
    if reaction.message.channel.id != channel.id:
        return
    if reaction.emoji == "👺" and reaction.message.id == watchathon_msg:
      role = discord.utils.get(user.guild.roles, name="Watchathon")
      await user.add_roles(role)

@client.command()
@commands.has_role("Pianosuki")
async def watchathon_role_assign(ctx):
    # Bot channel
    channel = client.get_channel(config.announce_channel)
    e = discord.Embed(title="React with :japanese_goblin: to add yourself to the @watchathon notification list.", description=f"Don't react if you don't wish to be pinged in the future.", color=0x3b88c3)
    message = await channel.send(embed = e)
    global watchathon_msg
    watchathon_msg = message.id
    await message.add_reaction("👺")

client.run(config.discord_token)
