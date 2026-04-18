"""Query parsing for sift-cli search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    raw: str
    text_terms: tuple[str, ...]
    phrases: tuple[str, ...]
    filename_terms: tuple[str, ...]
    content_terms: tuple[str, ...]
    exts: tuple[str, ...]
    path_terms: tuple[str, ...]
    after: float | None
    before: float | None
    size_min: int | None
    size_max: int | None


def parse_query(raw_query: str, *, now: datetime | None = None) -> ParsedQuery:
    raw = raw_query.strip()
    if not raw:
        return ParsedQuery(raw=raw_query, text_terms=(), phrases=(), filename_terms=(), content_terms=(), exts=(), path_terms=(), after=None, before=None, size_min=None, size_max=None)

    current = now or datetime.now(timezone.utc)
    tokens = _tokenize(raw_query)

    text_terms: list[str] = []
    phrases: list[str] = []
    filename_terms: list[str] = []
    content_terms: list[str] = []
    exts: list[str] = []
    path_terms: list[str] = []
    after: float | None = None
    before: float | None = None
    size_min: int | None = None
    size_max: int | None = None

    i = 0
    while i < len(tokens):
        token = tokens[i]
        lowered = token.casefold()

        separated_field = _parse_separated_field_clause(tokens, i)
        if separated_field is not None:
            field_name, value, next_index = separated_field
            if field_name == "filename":
                filename_terms.append(value)
            elif field_name == "content":
                content_terms.append(value)
            elif field_name == "ext":
                normalized = value.casefold().lstrip(".")
                if not normalized:
                    raise ValueError("invalid ext value")
                exts.append(normalized)
            elif field_name == "path":
                path_terms.append(value)
            elif field_name == "after":
                start, _ = _parse_date_value(value, current)
                after = start if after is None else max(after, start)
            elif field_name == "before":
                _, end = _parse_date_value(value, current)
                before = end if before is None else min(before, end)
            i = next_index
            continue

        from_phrase = _parse_from_phrase(tokens, i, current)
        if from_phrase is not None:
            start, end, next_index = from_phrase
            after = start if after is None else max(after, start)
            before = end if before is None else min(before, end)
            i = next_index
            continue

        if lowered == "this" and i + 1 < len(tokens) and tokens[i + 1].casefold() == "week":
            phrase_bounds = _parse_date_phrase("this week", current)
            assert phrase_bounds is not None
            start, end = phrase_bounds
            after = start if after is None else max(after, start)
            before = end if before is None else min(before, end)
            i += 2
            continue

        if lowered == "last" and i + 2 < len(tokens) and tokens[i + 1] == "7" and tokens[i + 2].casefold() == "days":
            phrase_bounds = _parse_date_phrase("last 7 days", current)
            assert phrase_bounds is not None
            start, end = phrase_bounds
            after = start if after is None else max(after, start)
            before = end if before is None else min(before, end)
            i += 3
            continue

        phrase_bounds = _parse_date_phrase(token, current)
        if phrase_bounds is not None:
            start, end = phrase_bounds
            after = start if after is None else max(after, start)
            before = end if before is None else min(before, end)
            i += 1
            continue

        size_bounds = _parse_size_filter(token)
        if size_bounds is not None:
            comparator, value = size_bounds
            if comparator in {"<", "<="}:
                size_max = value if size_max is None else min(size_max, value)
            elif comparator in {">", ">="}:
                size_min = value if size_min is None else max(size_min, value)
            else:
                size_min = value if size_min is None else max(size_min, value)
                size_max = value if size_max is None else min(size_max, value)
            i += 1
            continue

        field = _parse_field_clause(token)
        if field is not None:
            field_name, value = field
            if field_name == "filename":
                filename_terms.append(value)
            elif field_name == "content":
                content_terms.append(value)
            elif field_name == "ext":
                normalized = value.casefold().lstrip(".")
                if not normalized:
                    raise ValueError("invalid ext value")
                exts.append(normalized)
            elif field_name == "path":
                path_terms.append(value)
            elif field_name == "after":
                start, _ = _parse_date_value(value, current)
                after = start if after is None else max(after, start)
            elif field_name == "before":
                _, end = _parse_date_value(value, current)
                before = end if before is None else min(before, end)
            i += 1
            continue

        if _looks_like_size_operator(token):
            raise ValueError(f"invalid size value: {token}")
        if _looks_like_date_operator(token):
            raise ValueError(f"invalid date value: {token}")

        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            phrases.append(token[1:-1])
        else:
            text_terms.append(token)
        i += 1

    return ParsedQuery(
        raw=raw_query,
        text_terms=tuple(text_terms),
        phrases=tuple(phrases),
        filename_terms=tuple(filename_terms),
        content_terms=tuple(content_terms),
        exts=tuple(exts),
        path_terms=tuple(path_terms),
        after=after,
        before=before,
        size_min=size_min,
        size_max=size_max,
    )


def is_empty_query(parsed: ParsedQuery) -> bool:
    return not parsed.raw.strip() and not any(
        (
            parsed.text_terms,
            parsed.phrases,
            parsed.filename_terms,
            parsed.content_terms,
            parsed.exts,
            parsed.path_terms,
            parsed.after,
            parsed.before,
            parsed.size_min,
            parsed.size_max,
        )
    )


def is_filter_only_query(parsed: ParsedQuery) -> bool:
    return not parsed.text_terms and not parsed.phrases and not parsed.filename_terms and not parsed.content_terms and any(
        (parsed.exts, parsed.path_terms, parsed.after, parsed.before, parsed.size_min, parsed.size_max)
    )


def _tokenize(raw: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    for char in raw:
        if char == '"':
            current.append(char)
            in_quotes = not in_quotes
        elif char.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _parse_field_clause(token: str) -> tuple[str, str] | None:
    if ":" not in token:
        return None
    field, value = token.split(":", 1)
    field_name = field.casefold()
    if field_name not in {"filename", "content", "ext", "path", "after", "before"}:
        return None
    if not value:
        return None
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return field_name, value


def _parse_separated_field_clause(tokens: list[str], index: int) -> tuple[str, str, int] | None:
    token = tokens[index]
    lowered = token.casefold()
    if lowered not in {"filename:", "content:", "ext:", "path:", "after:", "before:"}:
        return None
    if index + 1 >= len(tokens):
        return None

    field_name = lowered[:-1]
    value = tokens[index + 1]
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    if not value:
        return None
    return field_name, value, index + 2


def _parse_date_phrase(token: str, current: datetime) -> tuple[float, float] | None:
    phrase = token.casefold().strip()
    today_start = current.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if phrase == "today":
        return today_start.timestamp(), (today_start + timedelta(days=1)).timestamp()
    if phrase == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        return yesterday_start.timestamp(), today_start.timestamp()
    if phrase == "this week":
        week_start = today_start - timedelta(days=today_start.weekday())
        return week_start.timestamp(), (week_start + timedelta(days=7)).timestamp()
    if phrase == "last 7 days":
        return (current.astimezone(timezone.utc) - timedelta(days=7)).timestamp(), current.astimezone(timezone.utc).timestamp()
    return None


def _parse_from_phrase(tokens: list[str], index: int, current: datetime) -> tuple[float, float, int] | None:
    if tokens[index].casefold() != "from":
        return None
    if index + 1 >= len(tokens):
        return None

    month = _MONTHS.get(tokens[index + 1].casefold())
    if month is None:
        return None

    year: int | None = None
    next_index = index + 2
    if index + 2 < len(tokens):
        year_token = tokens[index + 2]
        if re.fullmatch(r"\d{4}", year_token):
            year = int(year_token)
            next_index = index + 3

    current_utc = current.astimezone(timezone.utc)
    resolved_year = year if year is not None else _resolve_year_for_month(month=month, current=current_utc)
    start = datetime(resolved_year, month, 1, tzinfo=timezone.utc)
    return start.timestamp(), current_utc.timestamp(), next_index


def _resolve_year_for_month(*, month: int, current: datetime) -> int:
    if month > current.month:
        return current.year - 1
    return current.year


def _parse_date_value(value: str, current: datetime) -> tuple[float, float]:
    phrase_bounds = _parse_date_phrase(value, current)
    if phrase_bounds is not None:
        return phrase_bounds

    month_bounds = _parse_month_or_month_year(value, current)
    if month_bounds is not None:
        return month_bounds

    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip())
    if not match:
        raise ValueError(f"invalid date value: {value}")
    dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = dt.timestamp()
    return start, (dt + timedelta(days=1)).timestamp()


def _parse_month_or_month_year(value: str, current: datetime) -> tuple[float, float] | None:
    cleaned = value.strip().casefold()
    if not cleaned:
        return None

    parts = cleaned.split()
    if len(parts) not in {1, 2}:
        return None

    month = _MONTHS.get(parts[0])
    if month is None:
        return None

    if len(parts) == 1:
        year = _resolve_year_for_month(month=month, current=current.astimezone(timezone.utc))
    else:
        if not re.fullmatch(r"\d{4}", parts[1]):
            return None
        year = int(parts[1])

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start.timestamp(), end.timestamp()


def _parse_size_filter(token: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"size(<=|>=|<|>|=)(.+)", token.casefold())
    if not match:
        return None
    comparator = match.group(1)
    number = _parse_size_value(match.group(2))
    return comparator, number


def _parse_size_value(value: str) -> int:
    match = re.fullmatch(r"(\d+)([kmgt]?b)?", value.strip().casefold())
    if not match:
        raise ValueError(f"invalid size value: {value}")
    number = int(match.group(1))
    suffix = match.group(2) or ""
    multiplier = {"": 1, "b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}[suffix]
    return number * multiplier


def _looks_like_size_operator(token: str) -> bool:
    return token.casefold().startswith("size") and _parse_size_filter(token) is None


def _looks_like_date_operator(token: str) -> bool:
    lowered = token.casefold()
    return lowered.startswith("after:") or lowered.startswith("before:")
