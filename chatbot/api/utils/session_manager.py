import logging
import time

from chatbot.db.services import services

logger = logging.getLogger(__name__)
INACTIVITY_TTL = 24 * 60 * 60


class SessionManager:
    def __init__(self) -> None:
        self.inactivity_ttl: float = INACTIVITY_TTL
        self.users_in_process: dict[str, bool] = {}
        self.last_seen: dict[str, float] = {}
        self.busy_index: int = 0

    def touch_user(self, user_number: str) -> None:
        self.last_seen[user_number] = time.time()

    async def cleanup_inactive(self) -> None:
        now = time.time()
        to_delete: list[str] = []
        for phone, ts in self.last_seen.items():
            if now - ts > self.inactivity_ttl:
                to_delete.append(phone)

        for phone in to_delete:
            # await services.update_user(phone, resume=resume)
            # agent.chat_memory.delete_chat(phone)
            self.last_seen.pop(phone)
            logger.info(f"Cleaned inactive agent chat for {phone}")

            logger.info(f"Items cleaned for {phone}")

    async def check_user_availability(self, user_number: str) -> bool:
        if self.users_in_process.get(user_number):
            logger.warning(f"{user_number} en cola")
            return False

        return True

    def mark_user_busy(self, user_number: str) -> None:
        self.users_in_process[user_number] = True

    def mark_user_free(self, user_number: str) -> None:
        self.users_in_process[user_number] = False


session_manager = SessionManager()
