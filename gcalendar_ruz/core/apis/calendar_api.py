import os.path
import pickle
from aiohttp import ClientSession
from loguru import logger
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from ..utils import semlock, GOOGLE, token_check, handle_google_errors
from ..settings import settings


CREDS_PATH = settings.creds_path
TOKEN_PATH = settings.token_path
SCOPES = "https://www.googleapis.com/auth/calendar"


class GCalendar:
    SERVICE = GOOGLE

    def __init__(self):
        """
        Setting up calendar
        """

        self.refresh_token()
        self.period = settings.period

        self.HEADERS = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.creds.token}",
        }

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

        event["attendees"] = []
        if lesson.get("miem_lecturer_email"):
            event["attendees"] += [{"email": lesson["miem_lecturer_email"]}]
        if lesson.get("grp_emails"):
            event["attendees"] += [{"email": grp} for grp in lesson["grp_emails"]]

        event["reminders"] = {"useDefault": True}
        return event

    @handle_google_errors
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
        logger.info("Event created")

        return event_json

    @handle_google_errors
    @token_check
    @semlock
    async def delete_event(self, calendar_id, event_id):
        async with ClientSession() as session:
            res = await session.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers=self.HEADERS,
            )
            async with res:
                data = await res.json(content_type=None)

        if data is None:
            logger.info("Event deleted from Google Calendar")
        else:
            logger.error(data)
            return data

    @handle_google_errors
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

        logger.info(f"Update event returned code - {data.get('status')}.")
        return data

    @token_check
    async def get_events(self, calendar_id: str) -> dict:
        now = datetime.utcnow()
        nowISO = now.isoformat() + "Z"  # 'Z' indicates UTC time
        nowffISO = (now + timedelta(days=self.period)).isoformat() + "Z"
        params = {
            "timeMin": nowISO,
            "timeMax": nowffISO,
            "singleEvents": "True",
            "orderBy": "startTime",
            "maxResults": 2499,
        }
        async with ClientSession() as session:
            res = await session.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                headers=self.HEADERS,
                params=params,
            )
            async with res:
                data = await res.json()

        events = data.get("items", [])
        return events
