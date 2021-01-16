import asyncio

import discord
import typing
from discord.ext import commands


async def wf_msg_or_reaction(
    ctx: commands.Context,
    *,
    timeout: float = 120.0,
    checks: typing.List[callable] = None,
    message: discord.Message = None,
    **pairs
):
    """
    Waits for a message and/or a reaction, whichever comes first.

    :param ctx: You know what this is.
    :param timeout: the timeout to pass to wait_for. Defaults to 120s (2 minutes)
    :param checks: the custom checks to use. If not supplied, will auto-generate based on ctx
    :param message: The message to listen for reactions on. If not provided, assumes ctx.message.
    :param pairs: the {content: emoji} pairs.
    :return: the corresponding emoji
    """
    message = message or ctx.message
    if not checks:

        def reaction_check(r: discord.Reaction, u: discord.User):
            if str(r.emoji) in pairs.values():
                if u.id == ctx.author.id:
                    if r.message.id == message.id:
                        return True
            return False

        checks = [
            lambda m: m.content
            and m.content.lower() in pairs.keys()
            and m.author == ctx.author
            and m.channel == ctx.channel,
            reaction_check,
        ]

    tasks = [
        ctx.bot.wait_for("message", check=checks[0]),
        ctx.bot.wait_for("reaction_add", check=checks[1]),
    ]
    done, pending = await asyncio.wait(
        tasks, timeout=timeout or 120.0, return_when="FIRST_COMPLETED"
    )
    for task in pending:
        task.cancel()
    if not done:
        raise asyncio.TimeoutError()
    result = done.pop()
    if result.exception():
        raise result.exception()

    resolved = result.result()

    if isinstance(resolved, discord.Message):
        return pairs[resolved.content.lower()]
    return resolved[0].emoji


class Mapping(dict):
    def __missing__(self, key):
        return "{" + str(key) + "}"
