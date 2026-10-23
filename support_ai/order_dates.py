"""Bounded, server-owned parsing of order creation dates; no database access."""
import re
from datetime import date, datetime, timedelta, timezone


DATE_TEXT = re.compile(r'(?<!\d)(?:(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日?|\d{4}[-/]\d{1,2}[-/]\d{1,2})(?!\d)')
RELATIVE = re.compile(r'上个月|这个月|本个月|本月|上月|本周|这周|上周|今年|去年|今天|昨天|前天')
RANGE_LINK = re.compile(r'至|到|~|～|—|－|-|\bto\b', re.I)


def order_today():
    return datetime.now(timezone(timedelta(hours=8))).date()


def _relative_period(word, today):
    if word in ('今天', '昨天', '前天'):
        day = today - timedelta(days={'今天': 0, '昨天': 1, '前天': 2}[word])
        return day, day
    if word in ('本周', '这周', '上周'):
        start = today - timedelta(days=today.weekday())
        return (start - timedelta(days=7), start - timedelta(days=1)) if word == '上周' else (start, today)
    if word in ('本月', '这个月', '本个月'):
        return today.replace(day=1), today
    if word in ('上月', '上个月'):
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if word == '今年':
        return today.replace(month=1, day=1), today
    return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)


def creation_period(message, today=None):
    today = today or order_today()
    explicit = list(DATE_TEXT.finditer(message))
    relative = list(RELATIVE.finditer(message))
    day_ranges = list(re.finditer(r'(?:最近|近|过去)([1-9]\d{0,3})天', message))
    if len(day_ranges) > 1:
        raise ValueError('请明确一个时间范围，不要同时提供多个近N天条件。')
    recent_days = day_ranges[0] if day_ranges else None
    if sum(bool(item) for item in (explicit, relative, recent_days)) > 1:
        raise ValueError('请使用一种明确的日期范围，避免同时混用不同时间条件。')
    if re.search(r'(?:付款|支付|发货|收货|完成)(?:时间|日期)|'
                 r'(?:付款|支付|发货|收货|完成)(?:过)?的订单|'
                 r'\d{1,2}:\d{2}|\d{1,2}[点时]|之前|以前|之后|以后|截至|截止', message):
        raise ValueError('目前按订单创建日期查询，请提供开始和结束日期；包含起止日全天。')
    if explicit:
        if len(explicit) == 1 and (message[:explicit[0].start()].rstrip().endswith('从') or
                re.match(r'\s*(?:至|到|~|～|—|－|\bto\b)', message[explicit[0].end():], re.I)):
            raise ValueError('日期范围不完整，请同时提供开始日期和结束日期。')
        if len(explicit) > 2 or (len(explicit) == 2 and not RANGE_LINK.search(message[explicit[0].end():explicit[1].start()])):
            raise ValueError('请明确一个开始日期到结束日期的范围。')
        year = today.year
        days = []
        for match in explicit:
            try:
                if match.group(2):
                    year = int(match.group(1)) if match.group(1) else year
                    days.append(date(year, int(match.group(2)), int(match.group(3))))
                else:
                    day = date(*map(int, re.split(r'[-/]', match.group(0))))
                    year = day.year
                    days.append(day)
            except ValueError:
                raise ValueError('日期无效，请使用真实的年月日，例如2026-10-01。') from None
        leftover = DATE_TEXT.sub('', message)
        if re.search(r'\d{1,2}[月日]|\d{4}年', leftover):
            raise ValueError('日期范围不完整，请为起止日期写明月和日。')
        return days[0].isoformat(), days[-1].isoformat()
    if relative:
        if len(relative) == 1 and (message[:relative[0].start()].rstrip().endswith('从') or
                re.match(r'\s*(?:至|到|~|～|—|－|\bto\b)', message[relative[0].end():], re.I)):
            raise ValueError('日期范围不完整，请同时提供开始日期和结束日期。')
        if len(relative) > 2 or (len(relative) == 2 and not RANGE_LINK.search(message[relative[0].end():relative[1].start()])):
            raise ValueError('请明确要查询的一个时间范围。')
        start = _relative_period(relative[0].group(0), today)[0]
        end = _relative_period(relative[-1].group(0), today)[1]
        return start.isoformat(), end.isoformat()
    if recent_days:
        start = today - timedelta(days=int(recent_days[1]) - 1)
        return start.isoformat(), today.isoformat()
    if re.search(r'\d{4}[-/年]|\d{1,2}[月日]|前一|过去|近.{0,3}天|去年|上年|时间范围|期间|时间段', message):
        raise ValueError('请写明创建日期范围，例如2026-10-01至2026-10-23。')
    return None
