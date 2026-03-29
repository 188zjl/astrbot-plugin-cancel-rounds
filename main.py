import json
import re
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.star import star_map

PLUGIN_ID = "astrbot_plugin_cancel_rounds"
DEFAULT_COMMAND = "cancel"
CUSTOM_COMMAND_REGEX = r"^[/／][^\s]+(?:\s+.*)?$"


@register(
    PLUGIN_ID,
    "Codex",
    "删除当前会话最近几轮聊天记录，1 轮按 1 问 1 答计算。",
    "1.0.3",
)
class CancelRoundsPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any]):
        super().__init__(context)
        self.context = context
        self.config = config or {}

    def _custom_commands(self) -> set[str]:
        raw = str(self.config.get("custom_commands") or "")
        commands: set[str] = set()
        for item in re.split(r"[\r\n,]+", raw):
            normalized = self._normalize_command_name(item)
            if normalized:
                commands.add(normalized)
        return commands

    @staticmethod
    def _normalize_command_name(command: str) -> str:
        return (command or "").strip().lstrip("/／").strip().casefold()

    @staticmethod
    def _parse_slash_command(message: str) -> tuple[str, str] | None:
        matched = re.match(r"^[/／]([^\s]+)(?:\s+(.*))?$", (message or "").strip())
        if not matched:
            return None
        command_name = matched.group(1) or ""
        arg_text = matched.group(2) or ""
        return command_name, arg_text.strip()

    @staticmethod
    def _stop_plain_result(event: AstrMessageEvent, text: str):
        result = event.plain_result(text)
        result.stop_event()
        return result

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _get_livingmemory_plugin():
        for metadata in star_map.values():
            if (metadata.name or "").strip().lower() != "livingmemory":
                continue
            plugin = getattr(metadata, "star_cls", None)
            if plugin:
                return plugin
        return None

    async def _sync_livingmemory_after_cancel(
        self,
        event: AstrMessageEvent,
        removed_rounds: int,
    ) -> None:
        if removed_rounds <= 0:
            return

        plugin = self._get_livingmemory_plugin()
        if not plugin:
            return

        initializer = getattr(plugin, "initializer", None)
        if not initializer or not getattr(initializer, "is_initialized", False):
            return

        conversation_manager = getattr(initializer, "conversation_manager", None)
        memory_engine = getattr(initializer, "memory_engine", None)
        session_id = event.unified_msg_origin

        if not session_id or not conversation_manager:
            return

        store = getattr(conversation_manager, "store", None)
        conn = getattr(store, "connection", None) if store else None
        if not store or conn is None:
            return

        actual_count = await store.get_message_count(session_id)
        delete_count = min(max(removed_rounds * 2, 0), actual_count)
        new_actual_count = actual_count

        if delete_count > 0:
            cursor = await conn.execute(
                """
                DELETE FROM messages
                WHERE id IN (
                    SELECT id
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                )
                """,
                (session_id, delete_count),
            )
            deleted_messages = max(self._safe_int(cursor.rowcount, 0), 0)
            new_actual_count = max(actual_count - deleted_messages, 0)

            await conn.execute(
                """
                UPDATE sessions
                SET message_count = ?
                WHERE session_id = ?
                """,
                (new_actual_count, session_id),
            )
            await conn.commit()
            await conversation_manager.invalidate_cache(session_id)

        last_summarized_index = await conversation_manager.get_session_metadata(
            session_id, "last_summarized_index", 0
        )
        if self._safe_int(last_summarized_index, 0) > new_actual_count:
            await conversation_manager.update_session_metadata(
                session_id,
                "last_summarized_index",
                new_actual_count,
            )

        pending_summary = await conversation_manager.get_session_metadata(
            session_id, "pending_summary", None
        )
        if isinstance(pending_summary, dict):
            start_index = self._safe_int(pending_summary.get("start_index"), 0)
            end_index = self._safe_int(pending_summary.get("end_index"), 0)
            if start_index >= new_actual_count or end_index > new_actual_count:
                await conversation_manager.update_session_metadata(
                    session_id,
                    "pending_summary",
                    None,
                )

        db_connection = getattr(memory_engine, "db_connection", None) if memory_engine else None
        if db_connection is None:
            return

        cursor = await db_connection.execute(
            """
            SELECT id
            FROM documents
            WHERE json_extract(metadata, '$.session_id') = ?
              AND CAST(
                    COALESCE(
                        json_extract(metadata, '$.source_window.end_index'),
                        -1
                    ) AS INTEGER
                  ) > ?
            ORDER BY id DESC
            """,
            (session_id, new_actual_count),
        )
        rows = await cursor.fetchall()
        memory_ids = [self._safe_int(row[0], 0) for row in rows if self._safe_int(row[0], 0) > 0]

        for memory_id in memory_ids:
            await memory_engine.delete_memory(memory_id)

        if delete_count > 0 or memory_ids:
            logger.info(
                f"[{PLUGIN_ID}] 已同步 LivingMemory: session={session_id} | "
                f"deleted_messages={delete_count} | deleted_memories={len(memory_ids)} | "
                f"remaining_messages={new_actual_count}"
            )

    async def _remove_latest_rounds(
        self,
        event: AstrMessageEvent,
        rounds: int,
    ) -> tuple[int, int]:
        if rounds <= 0:
            raise ValueError("删除轮数必须大于 0。")

        cid = await self.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        if not cid:
            return 0, 0

        conversation = await self.context.conversation_manager.get_conversation(
            event.unified_msg_origin,
            cid,
        )
        if not conversation:
            return 0, 0

        history: list[dict[str, Any]] = []
        if conversation.history:
            try:
                history = json.loads(conversation.history or "[]")
            except Exception as exc:
                raise ValueError(f"当前会话历史解析失败：{exc}") from exc

        user_indexes = [
            index
            for index, message in enumerate(history)
            if isinstance(message, dict) and message.get("role") == "user"
        ]
        total_rounds = len(user_indexes)
        if total_rounds == 0:
            return 0, 0

        removed_rounds = min(rounds, total_rounds)
        cutoff_index = user_indexes[-removed_rounds]
        new_history = history[:cutoff_index]
        await self.context.conversation_manager.update_conversation(
            event.unified_msg_origin,
            conversation_id=conversation.cid,
            history=new_history,
        )
        await self._sync_livingmemory_after_cancel(event, removed_rounds)
        return removed_rounds, total_rounds

    async def _handle_cancel(self, event: AstrMessageEvent, rounds_text: str):
        raw_rounds = (rounds_text or "").strip()
        delete_rounds = 1
        if raw_rounds:
            if not raw_rounds.isdigit():
                return self._stop_plain_result(event, "用法：/cancel 或 /cancel 2")
            delete_rounds = int(raw_rounds)
            if delete_rounds <= 0:
                return self._stop_plain_result(event, "删除轮数必须大于 0。")

        try:
            removed_rounds, total_rounds = await self._remove_latest_rounds(
                event, delete_rounds
            )
        except Exception as exc:
            logger.error(
                f"[{PLUGIN_ID}] 删除会话历史失败: rounds={delete_rounds} | err={exc}",
                exc_info=True,
            )
            return self._stop_plain_result(event, f"删除聊天历史失败：{exc}")

        if removed_rounds == 0:
            return self._stop_plain_result(event, "当前会话没有可删除的聊天记录。")

        return self._stop_plain_result(
            event,
            f"删除了 {removed_rounds} 条信息。",
        )

    @filter.command(DEFAULT_COMMAND)
    async def cancel(self, event: AstrMessageEvent, rounds: str = ""):
        """cancel [轮数]"""
        yield await self._handle_cancel(event, rounds)

    @filter.regex(CUSTOM_COMMAND_REGEX)
    async def custom_cancel_command(self, event: AstrMessageEvent):
        parsed = self._parse_slash_command(event.get_message_str())
        if not parsed:
            return

        command_name, rounds = parsed
        normalized = self._normalize_command_name(command_name)
        if normalized == self._normalize_command_name(DEFAULT_COMMAND):
            return
        if normalized not in self._custom_commands():
            return

        yield await self._handle_cancel(event, rounds)
