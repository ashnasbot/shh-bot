from collections import defaultdict
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
from tinydb import TinyDB, Query


logging.basicConfig(encoding='utf-8', level=logging.INFO)

load_dotenv()
TOKEN = os.getenv("API_TOKEN")
LAST_MESSAGE = defaultdict(lambda: None)
WAITING_LIST = defaultdict(set)

db = TinyDB('store.json')

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="$shh_", intents=intents)


@bot.event
async def on_ready():
    """ Connected - say Hi. """
    logging.info("Connected to Discord!")
    for guild in bot.guilds:
        logging.info("In server '%s'", guild.name)


@bot.event
async def on_guild_remove(guild):
    """ Left a server - forget config. """
    logging.info("Leaving server '%s'", guild.name)
    if guild.id in WAITING_LIST:
        del WAITING_LIST[guild.id]
    Cfg = Query()
    db.remove(Cfg.guild == guild.id)


@bot.event
async def on_voice_state_update(member, before, after):
    """ Add or remove a member from the waiting list. """
    if not before.channel and after.channel:
        # They weren't in a channel, but are now
        guild = after.channel.guild
        Cfg = Query()
        if not db.search(Cfg.guild == guild.id):
            # We have no configuration for this guild, let them pass
            return

        await member.edit(mute = True)
        await member.edit(deafen = True)

        logging.info("Muted user %s in channel '%s'", member.name, after.channel.name)
        WAITING_LIST[guild.id].add(member)

        await update_message(guild, new=set([member]))
    elif not after.channel and before.channel:
        # They were in a channel, but have now left
        guild = before.channel.guild
        if member in WAITING_LIST[guild.id]:
            logging.info("User %s left the waiting list for channel '%s'", member.name, before.channel.name)
            WAITING_LIST[guild.id].remove(member)
            await update_message(guild)


@bot.event
async def on_reaction_add(reaction, user):
    """ Allow the user if they have reacted to us. """
    channel = reaction.message.channel
    guild = channel.guild

    if not LAST_MESSAGE[guild.id]:
        return

    if reaction.message.id == LAST_MESSAGE[guild.id].id:
        if str(reaction.emoji) == '🎤':
            await reaction.remove(user)
            await user.edit(mute = False)
            await user.edit(deafen = False)
            WAITING_LIST[guild.id].remove(user)
            logging.info("Unmuted user %s on %s", user.name, channel)
            await update_message(guild)


async def update_message(guild, new=set()):
    """ Add or remove pings from the waiting list message. """
    Cfg = Query()
    botconfig = db.search(Cfg.guild == guild.id)
    if not botconfig:
        return

    wait_list = WAITING_LIST[guild.id]

    if not wait_list:
        await rem_message(guild)
        return

    mentions = " ".join([m.mention for m in wait_list - new])
    new_mentions = " ".join([m.mention for m in new])
    message_channel = bot.get_channel(botconfig[0]['channel'])

    if new_mentions:
        await rem_message(guild)

        if len(wait_list) == 1:
            LAST_MESSAGE[guild.id] = await message_channel.send(f" {new_mentions} oi m8 react with '🎤' to chat")
        else:
            LAST_MESSAGE[guild.id] = await message_channel.send(f" {new_mentions} oi m8's react with '🎤' to chat")

    if mentions:
        if len(wait_list) == 1:
            await LAST_MESSAGE[guild.id].edit(content=f"{new_mentions} {mentions} oi m8 react with '🎤' to chat")
        else:
            await LAST_MESSAGE[guild.id].edit(content=f"{new_mentions} {mentions} oi m8's react with '🎤' to chat")


async def rem_message(guild):
    """ Remove our stored message, if it exists. """
    if LAST_MESSAGE[guild.id]:
        try:
            await LAST_MESSAGE[guild.id].delete()
        except discord.errors.NotFound:
            # Someone has already deleted our message, all good!
            pass
        del LAST_MESSAGE[guild.id]


@bot.command()
@commands.has_guild_permissions(manage_guild = True)
async def here(ctx, *args):
    """ Register the channel we're to ping people at. """
    logging.info("Set shh-ing enabled in '%s' via '%s'", ctx.guild.name, ctx.channel.name)
    guild = ctx.guild.id
    Cfg = Query()
    db.upsert({'guild': ctx.guild.id, 'channel': ctx.channel.id}, Cfg.guild == guild)
    await ctx.channel.send(f"I'll shh! people that join voice from here in {ctx.channel.mention}")
    await ctx.message.delete()


@bot.command()
@commands.has_guild_permissions(manage_guild = True)
async def off(ctx, *args):
    """ Unregister the channel and unshhsh everyone. """
    logging.info("Shh-ing disabled in '%s'", ctx.guild.name)
    guild = ctx.guild
    if guild.id in WAITING_LIST:
        for member in WAITING_LIST[guild.id]:
            await member.edit(mute = False)
            await member.edit(deafen = False)
        del WAITING_LIST[guild.id]
    await rem_message(guild)

    Cfg = Query()
    db.remove(Cfg.guild == guild.id)
    await ctx.message.delete()
    await ctx.channel.send(f"Shh! time is over")


if __name__ == "__main__":
    logging.info("Starting Shhhh! Bot")
    bot.run(TOKEN)