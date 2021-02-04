from aiohttp import ClientSession
from datetime import datetime, timedelta

from loguru import logger

from .nvr_api import Nvr_Api
from ..utils import camel_to_snake
from ..redis_caching.caching import cache
from ..utils import semlock, RUZ
from ..settings import settings


class RuzApi:
    SERVICE = RUZ

    def __init__(self, url: str = "http://92.242.58.221/ruzservice.svc"):
        self.url = url
        self.nvr_api = Nvr_Api()
        self.period = settings.period

    # building id МИЭМа = 92
    @cache
    @semlock
    async def get_auditoriumoid(self, building_id: int = 92):
        async with ClientSession() as session:
            res = await session.get(f"{self.url}/auditoriums?buildingoid=0")
            async with res:
                all_auditories = await res.json()

        return [
            room
            for room in all_auditories
            if room["buildingGid"] == building_id
            and room["typeOfAuditorium"] != "Неаудиторные"
        ]

    @cache
    @semlock
    async def get_lessons(self, ruz_room_id: str):
        """
        Get lessons in room for a specified period
        """

        needed_date = (datetime.today() + timedelta(days=self.period)).strftime(
            "%Y.%m.%d"
        )
        today = datetime.today().strftime("%Y.%m.%d")

        params = dict(
            fromdate=today, todate=needed_date, auditoriumoid=str(ruz_room_id)
        )

        async with ClientSession() as session:
            res = await session.get(f"{self.url}/lessons", params=params)
            async with res:
                data = await res.json(content_type=None)

        if res.status == 200:
            lessons = [await self.parse_lesson(class_) for class_ in data]
        else:
            lessons = []

        return lessons

    @semlock
    async def parse_lesson(self, lesson_ruz: dict) -> dict:
        """ Changes json about lesson from RUZ to be Erudite friendly """

        lesson = {}

        date = lesson_ruz.pop("date")
        date = date.split(".")
        lesson["date"] = "-".join(date)

        lesson["start_time"] = lesson_ruz.pop("beginLesson")
        lesson["end_time"] = lesson_ruz.pop("endLesson")

        lesson["summary"] = lesson_ruz["discipline"]
        lesson["location"] = f"{lesson_ruz['auditorium']}/{lesson_ruz['building']}"

        for key in lesson_ruz:
            new_key = f"ruz_{camel_to_snake(key)}"
            lesson[new_key] = lesson_ruz[key]

        lesson["ruz_url"] = lesson["ruz_url1"]

        if lesson["ruz_group"] is not None:
            stream = lesson["ruz_group"].split("#")[0]
            grp_emails = await self.nvr_api.get_course_emails(stream)
            if grp_emails != []:
                lesson[
                    "grp_emails"
                ] = []  # grp_emails !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
            else:
                logger.warning(f"Stream: {stream} has no groups")
        else:
            stream = ""
        lesson["course_code"] = stream

        lesson["description"] = (
            f"Поток: {stream}\n"
            f"Преподаватель: {lesson['ruz_lecturer']}\n"
            f"Тип занятия: {lesson['ruz_kind_of_work']}\n"
        )

        if lesson["ruz_url"]:
            lesson["description"] += f"URL: {lesson['ruz_url']}\n"

        if lesson.get("ruz_lecturer_email"):  # None or ""
            lesson["miem_lecturer_email"] = (
                lesson["ruz_lecturer_email"].split("@")[0] + "@miem.hse.ru"
            )

        return lesson
