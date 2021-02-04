from aiohttp import ClientSession
from loguru import logger
import time
from datetime import datetime
import pytz

from ..settings import settings
from ..utils import semlock, NVR
from .calendar_api import GCalendar


class Nvr_Api:
    NVR_API_URL = "https://nvr.miem.hse.ru/api/erudite"
    NVR_API_KEY = settings.nvr_api_key
    SERVICE = NVR
    calendar = GCalendar()

    def __init__(self) -> None:
        tzmoscow = pytz.timezone("Europe/Moscow")
        self.dt: str = (
            datetime.now().replace(microsecond=0, tzinfo=tzmoscow).isoformat()
        )

    @semlock
    async def get_course_emails(self, course_code: str):
        """ Gets emails from a GET responce from Erudite """

        async with ClientSession() as session:
            res = await session.get(
                f"{self.NVR_API_URL}/disciplines",
                params={"course_code": course_code},
                headers={"key": self.NVR_API_KEY},
            )
            async with res:
                data = await res.json()

        # If the responce is not list -> the responce is a message that discipline is not found, and it should not be analysed further
        if res.status == 200:
            grp_emails = data[0].get("emails")
        else:
            return []

        if grp_emails == [""]:
            return []

        return grp_emails

    @semlock
    async def add_lesson(self, lesson: dict) -> int:
        """ Posts a lesson to Erudite """

        async with ClientSession() as session:
            res = await session.post(
                f"{self.NVR_API_URL}/lessons",
                json=lesson,
                headers={"key": self.NVR_API_KEY},
            )
            async with res:
                data = await res.json()

        if res.status == 201:
            logger.info("Lesson added to Erudite")
        else:
            logger.error("Lesson could not be added to Erudite properly")

        return res.status, data

    @semlock
    async def delete_lesson(self, lesson_id: str):
        """ Deletes a lesson from Erudite """

        async with ClientSession() as session:
            res = await session.delete(
                f"{self.NVR_API_URL}/lessons/{lesson_id}",
                headers={"key": self.NVR_API_KEY},
            )
            async with res:
                await res.json()

        if res.status == 200:
            logger.info(f"Lesson with id: {lesson_id} deleted")
            return
        elif res.status == 404:
            logger.info(f"Lesson with id: {lesson_id} is not found in Erudite")
        else:
            logger.error("Erudite is not working properly...")

    @semlock
    async def update_lesson(self, lesson_id: str, lesson_data: dict):
        """ Updates a lesson in Erudite """

        async with ClientSession() as session:
            res = await session.put(
                f"{self.NVR_API_URL}/lessons/{lesson_id}",
                json=lesson_data,
                headers={"key": self.NVR_API_KEY},
            )
            async with res:
                await res.json()

        if res.status == 200:
            logger.info(f"Lesson with id: {lesson_id} updated")
        else:
            logger.error("Erudite is not working properly...")

    @semlock
    async def get_lesson(self, ruz_lesson_oid: int) -> list:
        """ Gets lesson from Erudite by it's ruz_lesson_oid """

        async with ClientSession() as session:
            res = await session.get(
                f"{self.NVR_API_URL}/lessons",
                params={"ruz_lesson_oid": ruz_lesson_oid, "fromdate": self.dt},
            )
            async with res:
                data = await res.json()

        if res.status != 200:
            # This means that there is no such lesson found in Erudite
            return False

        return data

    @semlock
    async def get_lessons_in_room(self, ruz_auditorium_oid: str) -> list:
        """ Gets all lessons from Erudite """

        async with ClientSession() as session:
            res = await session.get(
                f"{self.NVR_API_URL}/lessons",
                params={"ruz_auditorium_oid": ruz_auditorium_oid, "fromdate": self.dt},
            )
            async with res:
                lessons = await res.json()

        if res.status == 200:
            return lessons
        else:
            logger.info("Lesson not found")
            return []

    @semlock
    async def check_lesson(self, lesson: dict) -> list:
        """ Compares two lessons """

        data = await self.get_lesson(lesson["ruz_lesson_oid"])

        # No lesson found in Erudite, so it needs to be added
        if data is False:
            return "Not found", None, None

        lesson_id = data.pop("id")
        event_id = data.pop("gcalendar_event_id")
        data.pop("gcalendar_calendar_id")
        if data == lesson:
            return "Same", None, None

        # If code run up to this point, it means that lesson with such ruz_lesson_oid is found in Erudite, but it differs from the one in RUZ, so it needs to be updated
        return "Update", lesson_id, event_id

    @semlock
    async def check_delete_Erudite_lessons(
        self, lessons_ruz: list, ruz_auditorium_oid: str
    ):
        """ Check all lessons from room in Erudite, if the lesson doesn't exist in RUZ - delete it """

        lessons_erudite = await self.get_lessons_in_room(ruz_auditorium_oid)
        for lesson_erudite in lessons_erudite:
            flag = False
            for lesson_ruz in lessons_ruz:
                if lesson_ruz["ruz_lesson_oid"] == lesson_erudite["ruz_lesson_oid"]:
                    flag = True
                    break
                else:
                    continue
            if not flag:
                await self.delete_lesson(lesson_erudite["id"])
                await self.calendar.delete_event(
                    lesson_erudite["gcalendar_calendar_id"],
                    lesson_erudite["gcalendar_event_id"],
                )
                time.sleep(0.3)
