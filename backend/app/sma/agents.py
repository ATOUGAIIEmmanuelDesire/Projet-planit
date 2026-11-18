import asyncio
from typing import Dict, List, Optional, Any
from app.sma.protocol import FIPAACLMessage, Performative
from app.core.config import settings


class MessageBus:
    """Bus d'échange de messages inter-agents en mémoire avec diffusion WebSocket."""
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.ws_subscribers: List[asyncio.Queue] = []

    def subscribe_ws(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.ws_subscribers.append(q)
        return q

    def unsubscribe_ws(self, q: asyncio.Queue):
        if q in self.ws_subscribers:
            self.ws_subscribers.remove(q)

    async def broadcast(self, msg: FIPAACLMessage):
        await self.queue.put(msg)
        for sub in list(self.ws_subscribers):
            try:
                sub.put_nowait(msg)
            except asyncio.QueueFull:
                pass


class BaseAgent:
    def __init__(self, name: str, bus: MessageBus):
        self.name = name
        self.bus = bus
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def send(self, receiver: str, performative: Performative, content: dict, conversation_id: str = ""):
        msg = FIPAACLMessage(
            sender=self.name,
            receiver=receiver,
            performative=performative,
            content=content,
            conversation_id=conversation_id or self.name
        )
        await self.bus.broadcast(msg)


class RoomAgent(BaseAgent):
    """Agent représentant une salle de classe, un laboratoire ou une salle de travail."""
    def __init__(
        self,
        name: str,
        capacity: int,
        has_hvac_sensor: bool,
        is_lab: bool,
        bus: MessageBus,
        room_type: str = "Salle de cours"
    ):
        super().__init__(name, bus)
        self.capacity = capacity
        self.has_hvac_sensor = has_hvac_sensor
        self.is_lab = is_lab
        self.room_type = room_type
        self.is_workroom = "amphi" not in f"{name} {room_type}".lower()
        self.schedule: Dict[str, str] = {}  # clé horodatée (ex: 2026-11-17_08h00-12h00) -> course_id

    async def listen(self):
        while True:
            msg = await self.inbox.get()
            if msg.performative == Performative.CFP:
                slot = msg.content.get("timeslot")
                students = msg.content.get("students_count", 0)
                requires_lab = msg.content.get("requires_lab", False)
                workroom_only = msg.content.get("workroom_only", False)
                preferred_room = msg.content.get("preferred_room")

                # Validation des contraintes dures (Disponibilité sur l'horizon 8 semaines, Capacité, Type)
                is_available = slot not in self.schedule
                capacity_ok = self.capacity >= students
                lab_ok = not requires_lab or self.is_lab
                workroom_ok = not workroom_only or self.is_workroom

                if is_available and capacity_ok and lab_ok and workroom_ok:
                    hvac_kwh = settings.HVAC_KWH_SMART_SENSOR if self.has_hvac_sensor else settings.HVAC_KWH_STANDARD
                    hvac_saved_kwh = max(0.0, settings.HVAC_KWH_STANDARD - hvac_kwh)

                    # Score normalisé (0 - 100) avec bonus de stabilité par promotion sur 8 semaines
                    fill_ratio = min(1.0, students / max(1, self.capacity))
                    green_bonus = 25.0 if self.has_hvac_sensor else 0.0
                    promo_affinity_bonus = 15.0 if preferred_room == self.name else 0.0
                    capacity_score = fill_ratio * 60.0
                    total_score = round(min(100.0, capacity_score + green_bonus + promo_affinity_bonus), 2)

                    await self.send(
                        receiver=msg.sender,
                        performative=Performative.BID,
                        content={
                            "room": self.name,
                            "timeslot": slot,
                            "score": total_score,
                            "hvac_kwh": hvac_kwh,
                            "hvac_saved_kwh": hvac_saved_kwh,
                            "is_workroom": self.is_workroom
                        },
                        conversation_id=msg.conversation_id
                    )
                else:
                    await self.send(
                        receiver=msg.sender,
                        performative=Performative.REJECT_PROPOSAL,
                        content={"room": self.name, "reason": "Contrainte salle non respectée"},
                        conversation_id=msg.conversation_id
                    )
            elif msg.performative == Performative.ACCEPT_PROPOSAL:
                slot = msg.content.get("timeslot")
                course_id = msg.content.get("course_id")
                if slot:
                    self.schedule[slot] = course_id


class TeacherAgent(BaseAgent):
    """Agent représentant un enseignant et ses préférences de créneau."""
    def __init__(self, name: str, preferred_slots: List[str], unavailabilities: List[str], bus: MessageBus):
        super().__init__(name, bus)
        self.preferred_slots = preferred_slots
        self.unavailabilities = unavailabilities
        self.schedule: Dict[str, str] = {}

    async def listen(self):
        while True:
            msg = await self.inbox.get()
            if msg.performative == Performative.CFP:
                slot = msg.content.get("timeslot")
                if slot in self.unavailabilities or slot in self.schedule:
                    await self.send(
                        receiver=msg.sender,
                        performative=Performative.REJECT_PROPOSAL,
                        content={"teacher": self.name, "reason": "Enseignant indisponible"},
                        conversation_id=msg.conversation_id
                    )
                else:
                    pref_score = 100.0 if slot in self.preferred_slots else 65.0
                    await self.send(
                        receiver=msg.sender,
                        performative=Performative.BID,
                        content={"teacher": self.name, "pref_score": pref_score},
                        conversation_id=msg.conversation_id
                    )
            elif msg.performative == Performative.ACCEPT_PROPOSAL:
                slot = msg.content.get("timeslot")
                course_id = msg.content.get("course_id")
                if slot:
                    self.schedule[slot] = course_id


class CoordinatorAgent(BaseAgent):
    """Agent Coordinateur pilotant le protocole Contract Net (CNP) sur 8 semaines."""
    def __init__(self, name: str, room_agents: List[str], teacher_agents: List[str], bus: MessageBus):
        super().__init__(name, bus)
        self.room_agents = room_agents
        self.teacher_agents = teacher_agents

    async def negotiate_slot(
        self,
        course_id: str,
        timeslot: str,
        students_count: int,
        teacher_id: Optional[str],
        group_id: str,
        requires_lab: bool = False,
        workroom_only: bool = False,
        preferred_room: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        conv_id = f"CNP_{course_id}_{group_id}_{timeslot}"
        has_teacher = bool(teacher_id) and teacher_id != "Sans enseignant"

        # 1. Émission des CFP aux Salles (et à l'Enseignant uniquement si requis)
        for r_name in self.room_agents:
            await self.send(
                receiver=r_name,
                performative=Performative.CFP,
                content={
                    "course_id": course_id,
                    "timeslot": timeslot,
                    "students_count": students_count,
                    "requires_lab": requires_lab,
                    "workroom_only": workroom_only,
                    "preferred_room": preferred_room
                },
                conversation_id=conv_id
            )

        if has_teacher and teacher_id in self.teacher_agents:
            await self.send(
                receiver=teacher_id,
                performative=Performative.CFP,
                content={"course_id": course_id, "timeslot": timeslot},
                conversation_id=conv_id
            )

        # 2. Collecte des offres (BIDs) sous le délai imparti
        room_bids = []
        teacher_rejected = False
        teacher_score = 100.0 if not has_teacher else 65.0

        end_time = asyncio.get_event_loop().time() + settings.CNP_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < end_time:
            try:
                msg = await asyncio.wait_for(self.inbox.get(), timeout=0.05)
                if msg.conversation_id == conv_id:
                    if msg.performative == Performative.BID:
                        if "room" in msg.content:
                            room_bids.append(msg.content)
                        elif "teacher" in msg.content:
                            teacher_score = msg.content.get("pref_score", 65.0)
                    elif msg.performative == Performative.REJECT_PROPOSAL:
                        if "teacher" in msg.content:
                            teacher_rejected = True
            except asyncio.TimeoutError:
                pass

        if teacher_rejected or not room_bids:
            return None

        # 3. Sélection Pareto-optimale (Green-IT + Stabilité Salle Promotion + Préférence Enseignant)
        best_bid = max(room_bids, key=lambda b: (b["score"] * 0.65 + teacher_score * 0.35))
        winner_room = best_bid["room"]

        # 4. Confirmation de la réservation
        await self.send(
            receiver=winner_room,
            performative=Performative.ACCEPT_PROPOSAL,
            content={"course_id": course_id, "timeslot": timeslot},
            conversation_id=conv_id
        )

        if has_teacher and teacher_id in self.teacher_agents:
            await self.send(
                receiver=teacher_id,
                performative=Performative.ACCEPT_PROPOSAL,
                content={"course_id": course_id, "timeslot": timeslot},
                conversation_id=conv_id
            )

        return {
            "course_id": course_id,
            "timeslot": timeslot,
            "assigned_room": winner_room,
            "teacher_id": teacher_id if has_teacher else "Sans enseignant",
            "group_id": group_id,
            "score": round(best_bid["score"] * 0.65 + teacher_score * 0.35, 2),
            "hvac_kwh": best_bid["hvac_kwh"],
            "hvac_saved_kwh": best_bid["hvac_saved_kwh"],
            "resolution_method": "SMA_CNP"
        }