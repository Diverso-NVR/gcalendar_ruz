from datetime import datetime, timedelta
import asyncio
from loguru import logger
import time

from core.apis.ruz_api import RuzApi
from core.apis.calendar_api import GCalendar
from core.db.models import Session, Room, OnlineRoom, Record, UserRecord, User
from core.apis.nvr_api import Nvr_Api
from core.redis_caching.caching import redis_connect


class CalendarManager:
    def __init__(self):
        self.session = Session()
        self.ruz_api = RuzApi()
        self.nvr_api = Nvr_Api()
        self.calendar_api = GCalendar()

        self.ruz = self.session.query(OnlineRoom).filter_by(name="РУЗ").first()

    def __del__(self):
        self.session.close()

    async def get_rooms(self):
        offline_rooms = [room.name for room in self.session.query(Room).all()]

        rooms = await self.ruz_api.get_auditoriumoid()

        tasks = [
            self.synchronize_lessons_in_room(
                room["auditoriumOid"], offline_rooms, room["number"]
            )
            for room in rooms
        ]

        await asyncio.gather(*tasks)

        logger.info(
            f"Created events for {datetime.today().date() + timedelta(days=1)} - {datetime.today().date() + timedelta(days=self.ruz_api.period)}"
        )

    async def synchronize_lessons_in_room(
        self, room_id: str, offline_rooms: list, room_name: str
    ):
        lessons = await self.get_lessons_from_room(room_id)

        if lessons:
            logger.info(
                f"""
                Successfully got lessons for room {room_name}
                Synchronizing lessons in calendar and Erudite
                """
            )
            # Deletes lessons from Erudite if it doesn't exist in Ruz
            await self.nvr_api.check_delete_Erudite_lessons(lessons, room_id)
            time.sleep(0.2)

            for i in range(0, len(lessons), 10):
                chunk = lessons[i : i + 10]

                tasks = [
                    self.synchronize_lesson(room_id, lesson, offline_rooms)
                    for lesson in chunk
                ]
                await asyncio.gather(*tasks)

    async def get_lessons_from_room(self, room_id: str) -> list:
        """ Get lessons in room from ruz """

        try:
            lessons = await self.ruz_api.get_lessons(room_id)
        except Exception as err:
            lessons = None
            logger.error(err)

        return lessons

    async def synchronize_lesson(
        self,
        room_id: str,
        lesson: dict,
        offline_rooms: list,
    ):
        check_data = await self.nvr_api.check_lesson(lesson)
        status = check_data[0]

        # Lesson not found in Erudite, so we add it
        if status == "Not found":
            await self.add_lesson(lesson, offline_rooms)

        # Lesson found in Erudite, but the data of this lesson has to be updated
        elif status == "Update":
            lesson_id = check_data[1]
            event_id = check_data[2]
            await self.update_lesson(lesson, offline_rooms, lesson_id, event_id)
            time.sleep(0.6)

    async def add_lesson(self, lesson: dict, offline_rooms: list):
        """ Adds lesson to Erudite and Google Calendar """

        logger.info("Trying to add lesson")
        data = await self.test_post_lesson(lesson)
        code = data[0]
        erudite_lesson = data[1]
        if code == 201:
            event = await self.post_lesson(
                lesson, erudite_lesson["id"], self.ruz.calendar
            )
            time.sleep(0.6)

            if lesson["ruz_auditorium"] in offline_rooms:
                room = (
                    self.session.query(Room)
                    .filter_by(name=lesson["ruz_auditorium"])
                    .first()
                )
                self.create_record(room, event)

    async def update_lesson(
        self, lesson: dict, offline_rooms: list, lesson_id: str, event_id: str
    ):
        """ Updates lesson in Erudite and Google Calendar """

        logger.info("Updating ruz lesson")
        event = await self.calendar_api.update_event(
            self.ruz.calendar, event_id, lesson
        )
        lesson["gcalendar_event_id"] = event["id"]
        lesson["gcalendar_calendar_id"] = self.ruz.calendar
        await self.nvr_api.update_lesson(lesson_id, lesson)

        # if lesson["ruz_auditorium"] in offline_rooms:
        #     room = self.session.query(Room).filter_by(name=lesson["ruz_auditorium"]).first()
        #     self.create_record(room, event)

    async def test_post_lesson(self, lesson: dict):
        """ Post a lesson with empty event_id """

        lesson = dict(lesson)  # make copy

        lesson["gcalendar_event_id"] = ""
        lesson["gcalendar_calendar_id"] = ""

        data = await self.nvr_api.add_lesson(lesson)

        return data

    async def post_lesson(self, lesson: dict, lesson_id: str, calendar_id: str):
        """ Posts event to Google calendar and updates lesson in Erudite """

        event = await self.calendar_api.create_event(self.ruz.calendar, lesson)
        lesson["gcalendar_event_id"] = event["id"]
        lesson["gcalendar_calendar_id"] = calendar_id
        await self.nvr_api.update_lesson(lesson_id, lesson)

        return event

    def create_record(self, room: Room, event: dict):
        start_date = event["start"]["dateTime"].split("T")[0]
        end_date = event["end"]["dateTime"].split("T")[0]

        if start_date != end_date:
            return

        creator = (
            self.session.query(User).filter_by(email=event["creator"]["email"]).first()
        )
        if not creator:
            return

        new_record = Record()
        new_record.room = room
        new_record.update_from_calendar(**event)
        self.session.add(new_record)
        self.session.commit()

        user_record = UserRecord(user_id=creator.id, record_id=new_record.id)
        self.session.add(user_record)
        self.session.commit()

    async def delete_online_events(self):
        while True:
            events = await self.calendar_api.get_events(self.jitsi.calendar)
            if len(events) == 0:
                break
            for event in events:
                await self.calendar_api.delete_event(self.jitsi.calendar, event["id"])

        while True:
            events = await self.calendar_api.get_events(self.ruz.calendar)
            if len(events) == 0:
                break
            for event in events:
                await self.calendar_api.delete_event(self.ruz.calendar, event["id"])


@logger.catch
async def main():
    await redis_connect()
    manager = CalendarManager()

    await manager.get_rooms()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
