import asyncio
import discord
from discord.ext import commands
from apiclient.discovery import build

servers = {}
token = ''
prefix = ''
description = ''
text_channel = 'general'
voice_channel = ''
bot = commands.Bot(command_prefix=prefix, description=description)

if not discord.opus.is_loaded():
    discord.opus.load_opus('/usr/lib/libopus.so')

class Song:

    def __init__(self, youtubeid, title, duration, uploader):
        self.id = youtubeid
        self.title = title
        self.duration = duration
        self.uploader = uploader
        self.player = None

class MusicSession:

    def __init__(self, bot, channel, text_channel):
        self.bot = bot
        self.channel = channel
        self.text_channel = text_channel
        self.queue = asyncio.Queue()
        self.voiceClient = None
        self.play_next_song = asyncio.Event()
        self.songs = []
        self.current = None
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    @property
    def player(self):
        return self.current.player

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set())

    async def add_songs(self, songs):
        firstRun = True
        for song in songs:
            self.songs.append(song)
            await self.queue.put(song)
        await self.bot.send_message(self.text_channel, 'Added songs.')

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            print('1')
            self.current = await self.queue.get()
            print('2')
            opts = {
                    'default_search': 'auto',
                    'quiet': True,
                    }
            self.current.player = await self.voiceClient.create_ytdl_player('https://www.youtube.com/watch?v=' + self.current.id, ytdl_options=opts, after=self.toggle_next)
            print('3')
            await self.bot.send_message(self.text_channel, 'Playing song ' + self.current.title + ' uploaded by' + self.current.uploader)
            self.current.player.start()
            await self.play_next_song.wait()

class Voice:
    """
    Commands operating with voice channels.
    Can only be used with YouTube audio.
    """
    def __init__(self, bot, servers, voice_channel, text_channel):
        self.bot = bot
        self.servers = servers
        self.sessions = {}
        self.maxListeners = 30
        self.voice_channel = voice_channel
        self.text_channel = text_channel

    async def find_id(self, url):
        # Types: None = invalid, 1 = video, 2 = playlist
        id = None
        type = None
        if "list=" in url:
            type = 2
            string = url.split("list=")
            if "&" in string[1]:
                string = string[1].split("&")
                id = string[0]
            else:
                id = string[1]
        else:
            if "v=" in url:
                type = 1
                string = url.split("v=")
                id = string[1]
        print("find_id return value (id) =" + id)
        return (type, id)

    async def get_playlist_info(self, id):
        youtube = build('youtube', 'v3', developerKey='')
        playlists_resource = youtube.playlists()
        request = playlists_resource.list(part="snippet", maxResults=1, id=id)
        response = request.execute()
        items = response.get('items', [])
        playlist = items[0]['snippet']
        playlist_info = {"channel" : playlist['channelTitle'], "title" : playlist['title'], "published" : playlist['publishedAt']}
        return playlist_info


    def get_playlist_songs(self, id):
        youtube = build('youtube', 'v3', developerKey='')
        playlistItems_resource = youtube.playlistItems()
        request = playlistItems_resource.list(part='snippet', maxResults=50, playlistId=id)
        playlistEnd = False
        while not playlistEnd:
            songs = []
            if request is not None:
                response = request.execute()
                items = response.get('items', [])
                for song in items:
                    snippet = song['snippet']
                    resourceId = snippet['resourceId']
                    duration = 1
                    title = snippet['title']
                    uploader = snippet['channelTitle']
                    id = resourceId['videoId']
                    songs.append(Song(id, title, duration, uploader))
                yield songs
                request = playlistItems_resource.list_next(previous_request=request, previous_response=response)
            else:
                playlistEnd = True

    async def create_voice_client(self, channel, text_channel):
        self.sessions[channel.server] = MusicSession(self.bot, channel, text_channel)
        self.sessions[channel.server].voiceClient = await bot.join_voice_channel(channel)

    @commands.command(enabled=True, pass_context=True, no_pm=True)
    async def leave(self, ctx):
        if self.text_channel == '' or ctx.message.channel.name != self.text_channel:
            return
        session = sessions[ctx.message.server]
        if session.player is not None:
            if session.player.is_playing():
                session.player.stop()
        await session.voiceClient.disconnect()

    @commands.command(enabled=True, pass_context=True, no_pm=True)
    async def join(self, ctx,*args):
        if self.text_channel == '' or ctx.message.channel.name != self.text_channel:
            return
        channel_name = ' '.join(args)
        channel = None
        channels = {}
        if servers[ctx.message.server].get(channel_name) is not None:
            channels = servers[ctx.message.server][channel_name]

        if len(channels) == 1:
            if channels[0].type == discord.ChannelType.voice:
                channel = channels[0]
            else:
                await bot.say('That is not a voice channel')
        elif len(channels) > 1:
            counter = 0
            for cha in channels:
                if cha.type == discord.ChannelType.voice:
                    channel = cha
                    counter += 1
                if counter > 1:
                    channel = None
                    if ctx.message.author.voice_channel is not None:
                        if ctx.message.author.voice_channel.name == channel_name:
                            channel = ctx.message.author.voice_channel
                            await bot.say('More than one voice channel found. Assuming command users\' channel...')
                        else:
                            await bot.say('There is more than one voice channel with that name. You can tell me which one to join by first joining yourself and using the join command')
                    else:
                        await bot.say('There is more than one voice channel with that name. You can tell me which one to join by first joining yourself and using the join command')
        else:
            if channel_name == '':
                if ctx.message.author.voice_channel is not None:
                    channel = ctx.message.author.voice_channel
                else:
                    await bot.say('You are not in a voice channel. Either join one or specify one for the bot to join.')
            else:
                await bot.say('No such voice channel exists.')

        if channel is not None:
            #Todo: if already in a channel, leave channel and join new one
            try:
                if self.voice_channel == '' or channel == self.voice_channel:
                    await self.create_voice_client(channel, text_channel)
            except discord.ClientException:
                # This exception is triggered when bot is already in a channel
                await bot.say('Whoops... looks like there has been an error. (1)')
            except discord.InvalidArgument:
                await bot.say('Whoops... looks like there has been an error (2)')
            else:
                await bot.say('Joined channel ' + channel.name)

    @commands.command(enabled=True, pass_context=True, no_pm=True)
    async def play(self, ctx,  *urls):
        if self.text_channel == '' or ctx.message.channel.name != self.text_channel:
            return
        server = ctx.message.server
        if self.sessions.get(server) is not None:
            session = self.sessions.get(server)
            for url in urls:
                info = await self.find_id(url)
                type = info[0]
                id = info[1]
                songs = None
                #info[0] = None is invalid, 1 is video, 2 is playlist
                if type is not None:
                    if type == 2:
                        playlist_iterator = self.get_playlist_songs(id)
                        for songs in playlist_iterator:
                            await session.add_songs(songs)
                    else:
                        song = Song(id, None, None, None)
                        session.songs.append(song)
                        session.queue.put(song)
                else:
                    bot.say("This is not a valid YouTube video.")
        else:
            await bot.say("I'm not in a voice channel.")
        print('end of play')

@commands.command(enabled=True, pass_context=True, no_pm=True)
async def test(self):
    bot.say("Alive and replying!")

async def initialize_bot():
    for server in bot.servers:
        channels = {}
        for channel in server.channels:
            if channels.get(channel.name) is None:
                channels[channel.name] = [channel]
            else:
                channels[channel.name].append(channel)
        servers[server] = channels
    print(servers)

@bot.event
async def on_channel_create(channel):
    channels = servers[channel.server]
    if channels.get(channel.name) is None:
        servers[channel.server][channel.name] = [channel]
    else:
        servers[channel.server][channel.name].append(channel)
    print(servers[channel.server])

@bot.event
async def on_channel_delete(channel):
    channels = servers[channel.server]
    if len(channels.get(channel.name)) > 1:
        channels.get(channel.name).remove(channel)
    else:
        del servers[channel.server][channel.name]
    print(servers[channel.server])

@bot.event
async def on_channel_update(old, new):
    await on_channel_delete(old)
    await on_channel_create(new)
    print(servers)

@bot.event
async def on_ready():
    print('\nLogin succesful\n-----Info-----\nName: {0}\nID: {0.id}\n' .format(bot.user), end='')
    print('Guild(s): ', end='')
    servers = ''
    for i, server in enumerate(bot.servers):
        if i > 0:
            servers = '{0}, '.format(server) + servers
        else:
            servers = '{0}'.format(server)
    print(servers)
    await initialize_bot()


bot.add_cog(Voice(bot, servers, voice_channel, text_channel))
bot.run(token)
