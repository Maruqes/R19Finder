"""Discord Gateway bot: outgoing notifications, slash commands and persistent buttons."""
import asyncio
import logging
import uuid

import discord
from discord import app_commands

from worker import connect
from discord_integration import (
    DiscordError, api_request, authorize, command_summary, deliver_next,
    finish_rejection, prepare_rejection, read_token, text,
)


def load_config():
    with connect() as conn:
        return conn.execute('SELECT * FROM discord_settings WHERE id=1').fetchone()


def set_status(version, status, message, online=False):
    with connect() as conn:
        conn.execute('''UPDATE discord_settings SET status=%s, message=%s,
            heartbeat_at=CASE WHEN %s THEN now() ELSE NULL END WHERE id=1 AND version=%s''',
            (status, message, online, version))


def check_authorized(user_id, channel_id):
    with connect() as conn:
        authorize(conn, user_id, channel_id)


class FinderBot(discord.Client):
    def __init__(self, config):
        # Slash commands and component interactions do not require message-content access.
        super().__init__(intents=discord.Intents.none(), allowed_mentions=discord.AllowedMentions.none())
        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.delivery_task = None

        @self.tree.command(name='help', description='R19 Finder commands and actions')
        async def help_command(interaction: discord.Interaction):
            await self.respond_to_command(interaction, 'help')

        @self.tree.command(name='requests', description='View the last 10 part requests')
        async def requests_command(interaction: discord.Interaction):
            await self.respond_to_command(interaction, 'requests')

        @self.tree.command(name='schedules', description='View schedules and Discord notifications')
        async def schedules_command(interaction: discord.Interaction):
            await self.respond_to_command(interaction, 'schedules')

    async def setup_hook(self):
        channel = await self.fetch_channel(int(self.config['channel_id']))
        if not isinstance(channel, discord.TextChannel):
            raise ValueError('Choose a text channel in a Discord server.')
        guild = discord.Object(id=channel.guild.id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self):
        await asyncio.to_thread(set_status, self.config['version'], 'connected', 'Bot connected. Commands and notifications ready.', True)
        if self.delivery_task is None or self.delivery_task.done():
            self.delivery_task = asyncio.create_task(self.deliver_loop())

    async def deliver_loop(self):
        while not self.is_closed():
            await self.wait_until_ready()
            try:
                await asyncio.to_thread(deliver_next, connect, self.config['version'])
            except Exception as error:
                logging.error('Discord delivery failed (%s).', type(error).__name__)
            await asyncio.sleep(2)

    async def respond_to_command(self, interaction, command):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if command == 'help':
                await asyncio.to_thread(check_authorized, interaction.user.id, interaction.channel_id)
                message = ('/requests — latest requests\n/schedules — schedules and notifications\n'
                           'Reject — asks for confirmation and blacklists the listing for that request.\n'
                           'Restore listings in the app. These commands do not start AI searches.')
            else:
                message = await asyncio.to_thread(command_summary, connect, interaction.user.id, interaction.channel_id, command)
        except (PermissionError, ValueError) as error:
            message = str(error)
        except Exception as error:
            logging.error('Discord command failed (%s).', type(error).__name__)
            message = 'Unable to access the app. Try again.'
        await interaction.edit_original_response(content=message, allowed_mentions=discord.AllowedMentions.none())

    async def on_interaction(self, interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get('custom_id', '')
        if not custom_id.startswith('r19:'):
            return
        parts = custom_id.split(':')
        action = parts[1] if len(parts) > 1 else ''
        # Confirmation messages are ephemeral. Update that same message after either decision.
        await interaction.response.defer(ephemeral=True, thinking=action not in {'confirm', 'cancel'})
        try:
            if action == 'reject' and len(parts) == 4:
                search_id, index = uuid.UUID(parts[2]), int(parts[3])
                confirmation_id, title = await asyncio.to_thread(prepare_rejection, connect,
                    interaction.user.id, interaction.channel_id, interaction.message.id, search_id, index)
                view = discord.ui.View(timeout=300)
                view.add_item(discord.ui.Button(label='Confirm rejection', style=discord.ButtonStyle.danger,
                                              custom_id='r19:confirm:' + confirmation_id))
                view.add_item(discord.ui.Button(label='Cancel', style=discord.ButtonStyle.secondary,
                                              custom_id='r19:cancel:' + confirmation_id))
                await interaction.edit_original_response(
                    content=f"Reject **{text(title, 200)}**?\nThe listing will be removed from results and excluded from future searches for this request.",
                    view=view, allowed_mentions=discord.AllowedMentions.none())
                return
            if action in {'confirm', 'cancel'} and len(parts) == 3:
                config, message_id = await asyncio.to_thread(finish_rejection, connect,
                    interaction.user.id, interaction.channel_id, uuid.UUID(parts[2]), action == 'confirm')
                if action == 'confirm':
                    # The database is already committed; a failed cosmetic edit must not undo the rejection.
                    try:
                        await asyncio.to_thread(api_request, config, 'PATCH',
                            f"/channels/{config['channel_id']}/messages/{message_id}",
                            {'content': 'Part rejected · blacklisted for this request.',
                             'components': [], 'allowed_mentions': {'parse': []}})
                    except DiscordError:
                        logging.warning('Discord listing was rejected but its message could not be updated.')
                await interaction.edit_original_response(content='Part rejected. You can restore it in the app.'
                                                         if action == 'confirm' else 'Cancelled. The part was kept.', view=None)
                return
            raise ValueError('Invalid action.')
        except (PermissionError, ValueError, LookupError) as error:
            await interaction.edit_original_response(content=str(error), view=None)
        except Exception as error:
            logging.error('Discord interaction failed (%s).', type(error).__name__)
            await interaction.edit_original_response(content='Unable to complete the action. Try again.', view=None)

    async def on_error(self, event_method, *args, **kwargs):
        # Avoid logging interaction payloads, HTTP bodies or credentials.
        logging.error('Discord event failed: %s.', event_method)

    async def close(self):
        if self.delivery_task:
            self.delivery_task.cancel()
            await asyncio.gather(self.delivery_task, return_exceptions=True)
        await super().close()


async def run(lock):
    while True:
        await asyncio.to_thread(lock.execute, 'SELECT 1')
        config = await asyncio.to_thread(load_config)
        if not config['enabled'] or not config['bot_token']:
            await asyncio.sleep(5)
            continue
        bot = FinderBot(config)
        task = None
        try:
            token = read_token(config)
            task = asyncio.create_task(bot.start(token, reconnect=True))
            while True:
                done, _ = await asyncio.wait({task}, timeout=10)
                if done:
                    await task
                    break
                await asyncio.to_thread(lock.execute, 'SELECT 1')
                current = await asyncio.to_thread(load_config)
                if current['version'] != config['version'] or not current['enabled']:
                    break
                if bot.is_ready():
                    await asyncio.to_thread(set_status, config['version'], 'connected',
                                            'Bot connected. Commands and notifications ready.', True)
        except Exception as error:
            logging.error('Discord connection failed (%s).', type(error).__name__)
            await asyncio.to_thread(set_status, config['version'], 'error',
                'Unable to connect the bot. Check its token, channel access and applications.commands scope.')
            await asyncio.sleep(15)
        finally:
            await bot.close()
            if task:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(2)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    with connect() as lock:
        lock.autocommit = True
        if not lock.execute('SELECT pg_try_advisory_lock(190022) AS acquired').fetchone()['acquired']:
            raise SystemExit('Another Discord worker is already running.')
        asyncio.run(run(lock))
