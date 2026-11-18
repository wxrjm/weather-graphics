"""strftime that works the same on Windows and Linux: "%-d", "%-I", "%-m", "%-H", "%-M" (no leading zero) are
glibc-only and raise "Invalid format string" on Windows, so they're filled in here instead."""
import re

_NOPAD = {"d": "day", "m": "month", "H": "hour", "M": "minute", "y": None, "j": None}


def sft(dt, fmt):
    def rep(m):
        c = m.group(1)
        if c == "I":
            return str(dt.hour % 12 or 12)
        if c == "y":
            return str(dt.year % 100)
        if c == "j":
            return str(dt.timetuple().tm_yday)
        return str(getattr(dt, _NOPAD[c]))
    return dt.strftime(re.sub(r"%-([dmHMIyj])", lambda m: rep(m).replace("%", "%%"), fmt))
