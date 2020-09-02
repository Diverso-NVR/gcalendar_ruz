import requests
from datetime import datetime, timedelta
from pprint import pprint


class RuzApi:
    def __init__(self, url: str = 'http://92.242.58.221/ruzservice.svc'):
        self.url = url

    # building id МИЭМа = 92
    def get_auditoriumoid(self, building_id: int = 92):
        all_auditories = requests.get(
            f'{self.url}/auditoriums?buildingoid=0').json()

        return [room for room in all_auditories if room['buildingGid'] == building_id and room['typeOfAuditorium'] != 'Неаудиторные']

    # function that requests information about classes for 1 day from today and returns list of dicts
    def get_classes(self, ruz_room_id: str):
        """
        Get classes in room for 1 week
        """
        needed_date = (datetime.today() + timedelta(days=1)
                       ).strftime('%Y.%m.%d')

        res = requests.get(f"{self.url}/lessons?fromdate=" +
                           needed_date + "&todate=" + needed_date + "&auditoriumoid=" + str(ruz_room_id))

        classes = []
        for class_ in res.json():
            lesson = {'room': class_['auditorium']}
            lesson['start_time'] = datetime.strptime(
                (class_['date'] + class_['beginLesson']), '%Y.%m.%d%H:%M')
            lesson['end_time'] = datetime.strptime(
                (class_['date'] + class_['endLesson']), '%Y.%m.%d%H:%M')
            lesson['location'] = f"{class_['auditorium']}/{class_['building']}"
            if class_['group'] is not None:
                stream = class_['group'].split('#')[0]
            else:
                stream = ''
            lesson['description'] = (f"Поток: {stream}\n"
                                     f"Преподаватель: {class_['lecturer']}\n"
                                     f"Тип занятия: {class_['kindOfWork']}\n")

            classes.append(lesson)

        return classes
