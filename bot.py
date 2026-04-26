import discord
import anthropic
import os
import asyncio
import re
from discord.ext import commands
from gtts import gTTS

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
claude_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
historico_por_servidor = {}

SYSTEM_PROMPT = """Você é o Birulinha, o mascote fofinho e parceirão da galera na call do Discord! Você é MUITO animado, carinhoso e divertido. Chama todo mundo de parceiro, mano ou galera. Usa gírias brasileiras. Responda MUITO curto, máximo 2 frases curtas. NÃO use emojis pois vai ser lido em voz alta."""

def checar_chamado(mensagem):
    texto = mensagem.lower().strip()
    return any(texto.startswith(n) for n in ["birulinha", "biru", "birulinha,", "birulinha!", "birulinha?"])

def limpar_chamado(mensagem):
    return re.sub(r"^bi?ru?li?nha[,!?]?\s*", "", mensagem.strip(), flags=re.IGNORECASE).strip()

def limpar_para_voz(texto):
    texto = re.sub(r'[^\w\s.,!?áéíóúàâêôãõçÁÉÍÓÚÀÂÊÔÃÕÇ\-]', '', texto)
    return re.sub(r'\s+', ' ', texto).strip()

async def gerar_audio(texto):
    caminho = f"/tmp/biru_{abs(hash(texto))}.mp3"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: gTTS(text=limpar_para_voz(texto), lang='pt-br').save(caminho))
    return caminho

async def falar_na_call(vc, texto):
    if not vc or not vc.is_connected():
        return
    try:
        caminho = await gerar_audio(texto)
        while vc.is_playing():
            await asyncio.sleep(0.3)
        vc.play(discord.FFmpegPCMAudio(caminho))
        while vc.is_playing():
            await asyncio.sleep(0.3)
        try: os.remove(caminho)
        except: pass
    except Exception as e:
        print(f"Erro voz: {e}")

async def responder_com_ia(guild_id, autor, pergunta):
    if guild_id not in historico_por_servidor:
        historico_por_servidor[guild_id] = []
    h = historico_por_servidor[guild_id]
    h.append({"role": "user", "content": f"{autor}: {pergunta}"})
    if len(h) > 20:
        h = h[-20:]
        historico_por_servidor[guild_id] = h
    r = claude_client.messages.create(model="claude-sonnet-4-20250514", max_tokens=200, system=SYSTEM_PROMPT, messages=h)
    resposta = r.content[0].text
    h.append({"role": "assistant", "content": resposta})
    return resposta

def canal_texto(guild):
    for nome in ["geral", "general", "chat", "conversa"]:
        c = discord.utils.get(guild.text_channels, name=nome)
        if c: return c
    return guild.text_channels[0] if guild.text_channels else None

@bot.event
async def on_ready():
    print(f"Birulinha online! {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="a galera na call"))

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user: return
    guild = member.guild
    if after.channel and not before.channel and not guild.voice_client:
        try:
            vc = await after.channel.connect()
            c = canal_texto(guild)
            if c: await c.send(f"Oi {member.display_name}! Tô aqui na call! Me chama: **Birulinha, tudo bem?**")
            await asyncio.sleep(1)
            await falar_na_call(vc, f"Oi {member.display_name}, tô aqui parceiro!")
        except Exception as e:
            print(f"Erro: {e}")
    if before.channel and guild.voice_client:
        if len([m for m in before.channel.members if not m.bot]) == 0:
            await falar_na_call(guild.voice_client, "Valeu galera, até a próxima!")
            await guild.voice_client.disconnect()

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    await bot.process_commands(message)
    if not checar_chamado(message.content): return
    pergunta = limpar_chamado(message.content) or "oi"
    guild_id = message.guild.id if message.guild else message.author.id
    async with message.channel.typing():
        try:
            resposta = await responder_com_ia(guild_id, message.author.display_name, pergunta)
            await message.reply(resposta, mention_author=False)
            if message.guild and message.guild.voice_client:
                asyncio.create_task(falar_na_call(message.guild.voice_client, resposta))
        except Exception as e:
            print(f"Erro: {e}")
            await message.reply("Deu um bug aqui, tenta de novo!", mention_author=False)

@bot.command(name="entrar")
async def entrar(ctx):
    if ctx.author.voice:
        vc = await ctx.author.voice.channel.connect() if not ctx.guild.voice_client else ctx.guild.voice_client
        await ctx.send("Chegando na call!")
        await falar_na_call(vc, "Oi galera, tô aqui!")
    else:
        await ctx.send("Entra em um canal de voz primeiro!")

@bot.command(name="sair")
async def sair(ctx):
    if ctx.guild.voice_client:
        await falar_na_call(ctx.guild.voice_client, "Até mais galera!")
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Até mais!")
    else:
        await ctx.send("Nem tô na call!")

bot.run(os.environ["DISCORD_TOKEN"])
