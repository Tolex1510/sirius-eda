"""
Состояние для стримов, общее для всех вызовов внутри процесса сервиса.
"""
import queue
import threading
from collections import defaultdict, deque


class StatusBoard:
    """
    Счётчик изменений статусов доставок. TrackDelivery ждёт его, а не опрашивает БД в цикле:
    клиент узнаёт о новом статусе сразу после записи.
    """

    def __init__(self):
        self._changed = threading.Condition()
        self.version = 0

    def changed(self) -> None:
        with self._changed:
            self.version += 1
            self._changed.notify_all()

    def wait(self, seen: int, timeout: float) -> int:
        with self._changed:
            self._changed.wait_for(lambda: self.version != seen, timeout)
            return self.version


class ChatRooms:
    """
    Комнаты чата, одна на доставку. У каждого участника своя очередь входящих.
    Последние сообщения хранятся, чтобы зашедший позже видел начало разговора.
    """

    HISTORY = 20

    def __init__(self):
        self._lock = threading.Lock()
        self._members: dict[int, set[queue.Queue]] = defaultdict(set)
        self._history: dict[int, deque] = defaultdict(lambda: deque(maxlen=self.HISTORY))

    def join(self, room: int) -> queue.Queue:
        inbox = queue.Queue()
        with self._lock:
            for message in self._history[room]:
                inbox.put(message)
            self._members[room].add(inbox)
        return inbox

    def leave(self, room: int, inbox: queue.Queue) -> None:
        with self._lock:
            self._members[room].discard(inbox)

    def publish(self, room: int, message) -> None:
        with self._lock:
            self._history[room].append(message)
            for inbox in self._members[room]:
                inbox.put(message)
