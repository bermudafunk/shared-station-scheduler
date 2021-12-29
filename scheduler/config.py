from datetime import tzinfo
from zoneinfo import ZoneInfo

from decouple import config

CALENDAR_URL: str = config("CALENDAR_URL")

TIMEZONE: tzinfo = config("TIMEZONE", default="Europe/Berlin", cast=ZoneInfo)

UECP_SERIAL_PORT = config("UECP_SERIAL_PORT")
UECP_SERIAL_BAUDRATE = config("UECP_SERIAL_BAUDRATE", default=9600, cast=int)
