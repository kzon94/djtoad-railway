import os
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
from ytmusicapi import YTMusic
import asyncio

# 1. OBTENER TOKEN DE DISCORD DESDE VARIABLES DE ENTORNO
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    print("❌ No se ha encontrado el token de Discord. Asegúrate de configurarlo en las variables de entorno. Croak!")
    exit(1)

# 2. CONFIGURAR EL BOT DISCORD (INTENTS)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 3. FORZAR UN USER-AGENT DE NAVEGADOR EN YTMUSICAPI (SIN headers_raw)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/109.0.0.0 Safari/537.36"
)

# Inicializa YTMusic de forma "vacía"
yt = YTMusic()
# Fuerza manualmente el User-Agent en la sesión interna
# (solo necesario en versiones < 0.22.0 de ytmusicapi)
yt._session.headers['User-Agent'] = BROWSER_USER_AGENT

# 4. ALMACENAR COLAS DE REPRODUCCIÓN POR SERVIDOR
queues = {}

# -------------------------------------------------------------------
# Función para obtener una lista de canciones recomendadas
# -------------------------------------------------------------------
def get_song_list(song_id, exclude_song_id=None):
    """Devuelve una lista de (video_id, title) de canciones recomendadas."""
    recommendations = yt.get_watch_playlist(song_id)['tracks']
    recommended_songs = []
    for track in recommendations:
        if 'videoId' in track:
            video_id = track['videoId']
            if video_id != exclude_song_id:
                title = track.get('title', 'Sin título')
                recommended_songs.append((video_id, title))
            if len(recommended_songs) >= 10:
                break
    return recommended_songs

# -------------------------------------------------------------------
# Función para conectar al canal de voz del usuario
# -------------------------------------------------------------------
async def connect_to_voice(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ Debes estar en un canal de voz. Croak!")
        return None
    voice_channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        return await voice_channel.connect()
    elif ctx.voice_client.channel != voice_channel:
        return await ctx.voice_client.move_to(voice_channel)
    return ctx.voice_client

# -------------------------------------------------------------------
# Función para obtener la URL y el título de un video de YouTube
# usando yt-dlp con cookies (cookies.txt)
# -------------------------------------------------------------------
async def fetch_audio_info(video_id):
    """
    Obtiene la información del audio antes de reproducirlo.
    Usa el archivo 'cookies.txt' (presente en el proyecto) 
    para sortear bloqueos de YouTube que exijan iniciar sesión.
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        # Si tu archivo cookies.txt está en la misma carpeta:
        'cookiefile': 'cookies.txt'
    }

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        data = await asyncio.to_thread(
            youtube_dl.YoutubeDL(ydl_opts).extract_info,
            url,
            download=False
        )
        return data['url'], data.get('title', 'Sin título')
    except Exception as e:
        return None, f"❌ Error obteniendo audio: {e}, croak!"

# -------------------------------------------------------------------
# Función para reproducir la siguiente canción en la cola
# -------------------------------------------------------------------
async def play_next_song(ctx, attempts=0):
    MAX_ATTEMPTS = 3
    if attempts >= MAX_ATTEMPTS:
        await ctx.send("❌ No se pudo reproducir la siguiente canción. Croak!")
        return

    if ctx.guild.id in queues and queues[ctx.guild.id]:
        video_id, title = queues[ctx.guild.id].pop(0)
        url, _ = await fetch_audio_info(video_id)
        if not url:
            await ctx.send(f"❌ Error al obtener el audio para {title}, croak!")
            # Intentar la siguiente canción
            return await play_next_song(ctx, attempts + 1)

        vc = ctx.voice_client

        def after_playing(error):
            fut = asyncio.run_coroutine_threadsafe(
                play_next_song(ctx),
                bot.loop
            )
            try:
                fut.result()
            except Exception as e:
                print(f"Error en after_playing: {e}")

        vc.play(discord.FFmpegPCMAudio(url), after=after_playing)
        vc.source.title = title
        asyncio.run_coroutine_threadsafe(
            ctx.send(f"🎶 Reproduciendo: {title}, croak!"),
            bot.loop
        )
    else:
        await ctx.send("🚫 No hay más canciones en la cola. Desconectando... Croak!")
        if ctx.voice_client:
            await ctx.voice_client.disconnect()

# -------------------------------------------------------------------
# Comando '!play' para reproducir una canción
# -------------------------------------------------------------------
@bot.command()
async def play(ctx, *, song_name):
    vc = await connect_to_voice(ctx)
    if not vc:
        return

    await ctx.send(f"🔍 Buscando '{song_name}' y canciones recomendadas... Croak!")
    # Buscar la canción en YouTube Music
    search_results = yt.search(song_name, filter='songs')
    if not search_results or 'videoId' not in search_results[0]:
        await ctx.send("❌ No se encontraron resultados, croak!")
        return

    song_id = search_results[0]['videoId']
    # Obtener la URL y el título de la canción
    url, title = await fetch_audio_info(song_id)
    if not url:
        await ctx.send(title)  # Mensaje de error devuelto por fetch_audio_info
        return

    if vc.is_playing():
        vc.stop()

    def after_playing(error):
        fut = asyncio.run_coroutine_threadsafe(
            play_next_song(ctx),
            bot.loop
        )
        try:
            fut.result()
        except Exception as e:
            print(f"Error en after_playing: {e}")

    vc.play(discord.FFmpegPCMAudio(url), after=after_playing)
    vc.source.title = title
    await ctx.send(f"🎶 Reproduciendo: {title}, croak!")

    await ctx.send("⏳ Obteniendo canciones recomendadas... croak!")
    recommended_songs = get_song_list(song_id, exclude_song_id=song_id)
    queues[ctx.guild.id] = recommended_songs
    await ctx.send("✅ Lista de reproducción descargada exitosamente. Croak!")

# -------------------------------------------------------------------
# Comando '!add' para añadir una canción al inicio de la cola
# -------------------------------------------------------------------
@bot.command()
async def add(ctx, *, song_name):
    """Añade una canción al inicio de la cola de reproducción."""
    await ctx.send(f"🔍 Buscando '{song_name}' en YouTube Music... croak!")
    search_results = yt.search(song_name, filter='songs')
    if not search_results or 'videoId' not in search_results[0]:
        await ctx.send("❌ No se encontraron resultados. Croak!")
        return

    song_id = search_results[0]['videoId']
    title = search_results[0].get('title', 'Sin título')

    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []

    queues[ctx.guild.id].insert(0, (song_id, title))  # Insertar al inicio
    await ctx.send(f"✅ '{title}' ha sido añadida al inicio de la cola de reproducción. Croak!")

# -------------------------------------------------------------------
# Comando '!next' para saltar a la siguiente canción
# -------------------------------------------------------------------
@bot.command()
async def next(ctx):
    """Salta a la siguiente canción en la cola."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏩ Saltando a la siguiente canción... croak!")
    else:
        await ctx.send("🚫 No hay una canción reproduciéndose actualmente. Croak!")

# -------------------------------------------------------------------
# Comando '!list' para mostrar la cola de reproducción actual
# -------------------------------------------------------------------
@bot.command()
async def list(ctx):
    """Muestra la canción actual y la lista de canciones en la cola de reproducción."""
    message = ""
    vc = ctx.voice_client
    if vc and vc.is_playing() and hasattr(vc.source, 'title'):
        current_song = vc.source.title
        message += f"🎶 **Canción sonando:** {current_song}\n\n"
    else:
        message += "ℹ️ **No hay una canción reproduciéndose actualmente. Croak!**\n\n"

    if ctx.guild.id in queues and queues[ctx.guild.id]:
        message += "**Cola de reproducción:**\n"
        for index, (video_id, title) in enumerate(queues[ctx.guild.id], start=1):
            message += f"{index}. {title}\n"
    else:
        message += "ℹ️ La cola de reproducción está vacía. Croak!"

    await ctx.send(message)

# -------------------------------------------------------------------
# Comando '!pause' para pausar la reproducción
# -------------------------------------------------------------------
@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Reproducción pausada. Croak!")
    else:
        await ctx.send("🚫 No hay una canción reproduciéndose para pausar. Croak!")

# -------------------------------------------------------------------
# Comando '!resume' para reanudar la reproducción
# -------------------------------------------------------------------
@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Reproducción reanudada. Croak!")
    else:
        await ctx.send("🚫 No hay una canción pausada para reanudar. Croak!")

# -------------------------------------------------------------------
# Comando '!stop' para detener la reproducción y desconectar al bot
# -------------------------------------------------------------------
@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        queues.pop(ctx.guild.id, None)
        await ctx.send("⏹️ Bot desconectado y cola borrada. Croak!")
    else:
        await ctx.send("🚫 No estoy conectado a un canal de voz. Croak!")

# -------------------------------------------------------------------
# Comando '!dance1' para enviar un GIF de baile
# -------------------------------------------------------------------
@bot.command()
async def dance1(ctx):
    """Envía un GIF de baile."""
    gif_url = (
        "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExNGQweHk5MmpidXJrZDJidzcwbGR6ZzFpZTE1ZzFuMGs3"
        "emtwOHFmaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/pBDzxTAYdL6wRRdNTR/giphy.gif"
    )
    await ctx.send(gif_url)

# -------------------------------------------------------------------
# Comando '!dance2' para enviar otro GIF de baile
# -------------------------------------------------------------------
@bot.command()
async def dance2(ctx):
    """Envía otro GIF de baile."""
    gif_url = (
        "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHBvc3h4ZmlqeWRhNmY1Y2wyaHFrY29jb3M1aDdpdjB6"
        "M3QzaWc3ciZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9cw/gmUM6ag84nFnwaumx8/giphy.gif"
    )
    await ctx.send(gif_url)

# -------------------------------------------------------------------
# Evento cuando el bot está listo
# -------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ Tu rana favorita conectada como {bot.user}", flush=True)

# -------------------------------------------------------------------
# EJECUTAR EL BOT
# -------------------------------------------------------------------
bot.run(DISCORD_TOKEN)
