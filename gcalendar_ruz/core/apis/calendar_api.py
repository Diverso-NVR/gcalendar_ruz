import os.path
import pickle
from aiohttp import ClientSession
from loguru import logger

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..utils import semlock, GOOGLE, token_check


CREDS_PATH = "core/creds/credentials.json"
TOKEN_PATH = "core/creds/tokenCalendar.pickle"
SCOPES = "https://www.googleapis.com/auth/calendar"


class GCalendar:
    SERVICE = GOOGLE

    def __init__(self):
        """
        Setting up calendar
        """

        self.refresh_token()

        self.HEADERS = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.creds.token}",
        }

        self.service = build("calendar", "v3", credentials=self.creds)

    def refresh_token(self):
        self.creds = None
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "rb") as token:
                self.creds = pickle.load(token)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "wb") as token:
                pickle.dump(self.creds, token)

    def parse_lesson_to_event(self, lesson: dict) -> dict:
        """
        format: "%Y-%m-%dT%H:%M:%S"
        ex: 2019-11-12T15:00
        """

        event = {
            "summary": lesson["summary"],
            "location": lesson["location"],
            "start": {
                "dateTime": f"{lesson['date']}T{lesson['start_time']}:00",
                "timeZone": "Europe/Moscow",
            },
            "end": {
                "dateTime": f"{lesson['date']}T{lesson['end_time']}:00",
                "timeZone": "Europe/Moscow",
            },
            "description": lesson["description"],
        }

        # if lesson.get("ruz_lecturer_email"):
        # event["attendees"] = [{"email": lesson["ruz_lecturer_email"]}]
        # if lesson.get("grp_emails"):
        # event["attendees"] += [{"email": grp} for grp in lesson["grp_emails"]]

        # event["reminders"] = {"useDefault": True}

        return event

    @token_check
    @semlock
    async def create_event(
        self,
        calendar_id: str,
        lesson: dict,
    ) -> str:
        event = self.parse_lesson_to_event(lesson)

        async with ClientSession() as session:
            event_post = await session.post(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                json=event,
                headers=self.HEADERS,
            )
            async with event_post:
                event_json = await event_post.json()

        return event_json

    @token_check
    @semlock
    async def delete_event(self, calendar_id, event_id):
        async with ClientSession() as session:
            await session.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers=self.HEADERS,
            )

    @token_check
    @semlock
    async def update_event(self, calendar_id: str, event_id: str, lesson: dict) -> str:
        """ Updates an event in the google calendar """

        event = self.parse_lesson_to_event(lesson)

        async with ClientSession() as session:
            res = await session.put(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                json=event,
                headers=self.HEADERS,
            )
            async with res:
                data = await res.json()

        logger.info(f"Update event returned code - {data.get('code')}.")
        return data

    ############## Убрать на проде!
    @token_check
    @semlock
    async def get_event(self, calendar_id: str, event_id: str) -> dict:
        async with ClientSession() as session:
            events_result = await session.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers=self.HEADERS,
            )
            async with events_result:
                events_result = await events_result.json()

        print(events_result)
        return events
