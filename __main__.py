from collections import defaultdict
import logging
import os
import inspect

import discord
from discord.ext import commands
from dotenv import load_dotenv
from tinydb import TinyDB, Query

logging.basicConfig(encoding='utf-8', level=logging.INFO)

load_dotenv()
TOKEN = os.getenv("API_TOKEN")
DEFAULT_EMOJI = "❤️"
LAST_MESSAGE = defaultdict(lambda: None)
WAITING_LIST = defaultdict(set)
EMOJI_MESSAGE = defaultdict(lambda: None)

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

    Cfg = Query()
    botconfig = db.search(Cfg.guild == guild.id)
    if not botconfig:
        return
    channel_cfg = botconfig[0]

    if LAST_MESSAGE[guild.id]:
        if reaction.message.id == LAST_MESSAGE[guild.id].id:
            if str(reaction.emoji) == channel_cfg['emoji']:
                if user in WAITING_LIST[guild.id]:
                    await reaction.remove(user)
                    await user.edit(mute = False)
                    await user.edit(deafen = False)
                    WAITING_LIST[guild.id].remove(user)
                    logging.info("Unmuted user %s on %s", user.name, channel)
                    await update_message(guild)
            return

    if EMOJI_MESSAGE[guild.id]:
        if reaction.message.id == EMOJI_MESSAGE[guild.id].id:
            db.update({'emoji': str(reaction.emoji)}, Cfg.guild == guild.id)
            await EMOJI_MESSAGE[guild.id].delete()
            del EMOJI_MESSAGE[guild.id]
            channel = reaction.message.channel 
            await channel.send(f"Reaction set to {str(reaction.emoji)}")
            logging.info("Set emoji to %s on '%s'", str(reaction.emoji), channel)


async def update_message(guild, new=set()):
    """ Add or remove pings from the waiting list message. """
    Cfg = Query()
    botconfig = db.search(Cfg.guild == guild.id)
    if not botconfig:
        return
    channel_cfg = botconfig[0]

    wait_list = WAITING_LIST[guild.id]

    if not wait_list:
        await rem_message(guild)
        return

    mentions = " ".join([m.mention for m in wait_list - new])
    new_mentions = " ".join([m.mention for m in new])
    message_channel = bot.get_channel(channel_cfg['channel'])

    if new_mentions:
        await rem_message(guild)
        msg = f""" {new_mentions}
        You entered the voice chat.
        Welcome to {message_channel.mention} where voice/chat meet. 
        You're currently deafened/muted.
        Please react to this message with {channel_cfg['emoji']} to undeafen/unmute"""
        LAST_MESSAGE[guild.id] = await message_channel.send(inspect.cleandoc(msg))

    if mentions:
        msg=f"""{new_mentions} {mentions}
        You entered the voice chat.
        Welcome to {message_channel.mention} where voice/chat meet. 
        You're currently deafened/muted.
        Please react to this message with {channel_cfg['emoji']} to undeafen/unmute"""
        await LAST_MESSAGE[guild.id].edit(content=inspect.cleandoc(msg))
    
    if LAST_MESSAGE:
        await LAST_MESSAGE[guild.id].add_reaction(channel_cfg['emoji'])


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
    Cfg = Query()

    botconfig = db.search(Cfg.guild == ctx.guild.id)
    if botconfig:
        channel_cfg = botconfig[0]
        emoji = channel_cfg.get('emoji', DEFAULT_EMOJI)
    else:
        emoji = DEFAULT_EMOJI

    db.upsert({'guild': ctx.guild.id, 'channel': ctx.channel.id, 'emoji': emoji}, Cfg.guild == ctx.guild.id)
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

@bot.command()
@commands.has_guild_permissions(manage_guild = True)
async def emoji(ctx):
    await ctx.message.delete()
    EMOJI_MESSAGE[ctx.guild.id] = await ctx.channel.send(f"React to this message with the emoji you want to use.")


if __name__ == "__main__":
    logging.info("Starting Shhhh! Bot")
    bot.run(TOKEN)