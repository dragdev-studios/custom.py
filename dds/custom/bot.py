import asyncio
import random
from sys import stderr
from textwrap import shorten
from traceback import print_exc
from typing import Optional

import discord
from discord.ext.commands import Bot as _Bot
from humanize import intcomma as ic


class LogEvents(dict):
    def __init__(
            self,
            *,
            connection: bool = True,
            on_ready: bool = True,
            commands: bool = True,
            command_errors: bool = True,
    ):
        super().__init__(
            connection=connection,
            on_ready=on_ready,
            commands=commands,
            command_errors=command_errors,
        )


class DMChannelGuild:
    def __init__(self, context):
        self.id = "@me"
        self.context = context

    def __getattr__(self, item):
        return getattr(self.context.channel, item)


class QOLBot(_Bot):
    """commands.Bot with quality of life improvements."""

    def __init__(self, *args, **kwargs):
        self.queue = asyncio.Queue(kwargs.pop("max_queue_size", 30))
        self._queue_worker = self.loop.create_task(self.__queue_worker())
        super().__init__(*args, **kwargs)

    async def __queue_worker(self):
        while True:
            job = await self.queue.get()
            try:
                await job
            except (
                    Exception,
                    BaseException,
            ) as e:  # the two exceptions here are to please linters.
                print(
                    "(QOLBot Worker) Failed to do job ID '{}' - Skipping.", file=stderr
                )
                print_exc()
            finally:
                try:
                    self.queue.task_done()
                except asyncio.QueueEmpty:
                    pass  # this can be raised during race conditions, somehow

    async def close(self):
        self._queue_worker.cancel("Bot is logging out.")
        await super().close()

    def get_message(self, id: int) -> Optional[discord.Message]:
        """Gets a message.

        This behaves similarly to get_channel and other get methods, in that it returns None if not found.

        :param id: the message ID
        :returns Optional[discord.Message]: the resulting message"""
        return discord.utils.get(self.cached_messages, id=id)


class VerboseBot(_Bot):
    """A bot that logs stuff to a channel when it is called."""

    def __init__(self, *args, **kwargs):
        self._logging_channel_id = kwargs.pop("log_channel", None)
        if self._logging_channel_id and not isinstance(self._logging_channel_id, int):
            raise TypeError("Logging channel ID is not an integer.")
        self._logging_events = kwargs.pop("log_events", LogEvents())
        if not isinstance(self._logging_events, (dict, LogEvents)):
            raise TypeError("Logging events is not a dictionary or LogEvents class.")
        self._log_channel = None
        super().__init__(*args, **kwargs)

        # We need to now passively add listeners so that they can confidently bubble down, instead of us capturing them.
        self.add_listener(self._on_command_error, "on_command_error")
        self.add_listener(self._on_ready, "on_ready")

    async def _log_bg(self, message: str = None, *, shorten_if_needed: bool = True):
        if not self._log_channel:
            if not self.is_ready():
                await self.wait_until_ready()
            self._log_channel = self.get_channel(self._logging_channel_id)
        if not self._log_channel:
            return

        if self._log_channel.permissions_for(
                self._log_channel.guild.me
        ).manage_webhooks:
            webhooks = await self._log_channel.webhooks()
            if not webhooks:
                webhook = await self._log_channel.create_webhook(
                    name="VerboseBot Logging"
                )
            else:
                webhook = random.choice(webhooks)
            await webhook.send(
                shorten(message, 2000)
                if shorten_if_needed and len(message) > 2000
                else message
            )
        else:
            if self._log_channel.permissions_for(
                    self._log_channel.guild.me
            ).send_messages:
                await self._log_channel.send(
                    shorten(message, 2000)
                    if shorten_if_needed and len(message) > 2000
                    else message
                )
        print(message)

    def log(self, message, *, shorten_if_needed: bool = True):
        return self.loop.create_task(
            self._log_bg(message, shorten_if_needed=shorten_if_needed)
        )

    async def on_connect(self):
        if self._logging_events["connection"]:
            self.log("[\N{white heavy check mark} CONNECTION] Connected to discord!")

    async def on_disconnect(self):
        if self._logging_events["connection"]:
            self.log("[\N{cross mark} CONNECTION] Disconnected from discord!")

    async def on_command(self, ctx):
        if not ctx.guild:
            ctx.guild = DMChannelGuild(ctx)
        if self._logging_events["commands"]:
            self.log(
                f"[\N{white heavy check mark} COMMANDS] {ctx.author} (`{ctx.author.id}`) is running command "
                f"{ctx.command.qualified_name} in {ctx.channel} (`{ctx.channel.id}`), in {ctx.guild} (`"
                f"{ctx.guild.id}`) with {len(ctx.args) + len(ctx.kwargs)} arguments and permissions"
                f" (for the author) `{ctx.channel.permissions_for(ctx.author).value}` and "
                f"(for the bot) `{ctx.channel.permissions_for(ctx.me).value}`."
            )

    async def on_command_completion(self, ctx):
        if not ctx.guild:
            ctx.guild = DMChannelGuild(ctx)
        if self._logging_events["commands"]:
            self.log(
                f"[\N{white heavy check mark} COMMANDS] {ctx.author} (`{ctx.author.id}`) is finished running "
                f"command "
                f"{ctx.command.qualified_name} in {ctx.channel} (`{ctx.channel.id}`), in {ctx.guild} (`"
                f"{ctx.guild.id}`) with {len(ctx.args) + len(ctx.kwargs)} arguments."
            )

    async def _on_command_error(self, ctx, err):
        if not ctx.guild:
            ctx.guild = DMChannelGuild(ctx)
        if self._logging_events["commands"]:
            self.log(
                f"[\N{cross mark} COMMANDS] {ctx.author} (`{ctx.author.id}`) is finished running "
                f"command "
                f"{ctx.command.qualified_name} in {ctx.channel} (`{ctx.channel.id}`), in {ctx.guild} (`"
                f"{ctx.guild.id}`) with {len(ctx.args) + len(ctx.kwargs)} arguments. However, there was an error:\n"
                f"```py\n{err.__class__.__name__}: {getattr(err, 'msg', str(err))}\n```"
            )

    async def _on_ready(self):
        if self._logging_events["connection"]:
            self.log(
                f"[\N{white heavy check mark} CONNECTION] Bot is now ready!\n"
                f"{ic(len(self.guilds))} Guilds,"
                f"{ic(len(set(self.get_all_channels())))} Channels,"
                f"{ic(len(self.users))} Users"
            )
