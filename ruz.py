import requests
from datetime import datetime, timedelta
from calendarSettings import create_event_

#function that requests information about classes for 15 days from today and returns list of dicts
def get_classes(aud_id):

    # getting current date (from_date) and a month after (to_date)
    from_date = datetime.today().strftime('%Y.%m.%d')
    to_date = (datetime.strptime(from_date, '%Y.%m.%d') + timedelta(days=15)).strftime('%Y.%m.%d')


    classes = requests.get("http://92.242.58.221/ruzservice.svc/lessons?fromdate=" + from_date + "&todate=" + to_date + "&auditoriumoid=" + aud_id).json()


    list_of_classes = []
    for i in range(len(classes)):
        lesson = {}
        lesson['room_name'] =str(classes[i]['auditorium'])
        lesson['start_time'] = str(datetime.strptime((classes[i]['date']  + classes[i]['beginLesson']), '%Y.%m.%d%H:%M'))
        lesson['lesson_name'] = classes[i]['discipline']
        lesson['lecturer'] = classes[i]['lecturer']
        list_of_classes.append(lesson.copy())
    return list_of_classes

def add_classes_to_calendar(list_of_classes):
    for i in range(len(list_of_classes)):
        create_event_(room_name=list_of_classes[i]['room_name'], start_time=list_of_classes[i]['start_time'], summary=list_of_classes[i]['lesson_name'], lecturer= list_of_classes[i]['lecturer'])


# айди 504 аудитории
aud_id = '3360'

add_classes_to_calendar(get_classes(aud_id))