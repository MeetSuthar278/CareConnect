"""Bounded SQL list queries with validated, whitelisted ordering and lookahead."""
from dataclasses import dataclass, field

from flask import abort, request, url_for
from sqlalchemy import text


@dataclass
class Pagination:
    page: int = 1
    page_size: int = 20
    sort: str = 'newest'
    order_by: str = ''
    endpoint: str = ''
    params: dict = field(default_factory=dict)
    sort_options: dict = field(default_factory=dict)
    has_next: bool = False
    displayed: int = 0

    @classmethod
    def from_request(cls, sorts, default='newest', *, endpoint=None):
        try:
            page = int(request.args.get('page', '1'))
            size = int(request.args.get('page_size', '20'))
        except (ValueError, TypeError):
            abort(400, description='Choose a valid page number and records per page.')
        if not 1 <= page <= 100000 or size not in {10, 20, 50}:
            abort(400, description='Choose a page from 1 to 100000 and 10, 20 or 50 records per page.')
        sort = request.args.get('sort', default)
        if sort not in sorts:
            abort(400, description='Choose one of the available sort options.')
        # Never forward url_for control arguments such as _scheme/_external.
        params = {key: request.args[key] for key in
                  ('search', 'category', 'delivery', 'status', 'priority', 'org_id', 'attention')
                  if key in request.args}
        params.update(sort=sort, page_size=size)
        return cls(page, size, sort, sorts[sort][1], endpoint or request.endpoint,
                   params, {key: value[0] for key, value in sorts.items()})

    def url(self, page):
        return url_for(self.endpoint, **dict(self.params, page=page))

    @property
    def current_query(self):
        return dict(self.params, page=self.page)

    @property
    def start(self):
        return (self.page - 1) * self.page_size + 1 if self.displayed else 0

    @property
    def end(self):
        return self.start + self.displayed - 1 if self.displayed else 0


def page_rows(database, sql, params, pagination):
    """ORDER BY comes only from server-owned mappings, values remain bound.

    One extra row detects Next without an additional COUNT query. Do not invent
    total-page counts when the application has not queried a total.
    """
    rows = database.execute(text(sql + ' ORDER BY ' + pagination.order_by +
                                 ' LIMIT :page_limit OFFSET :page_offset'),
                            dict(params, page_limit=pagination.page_size + 1,
                                 page_offset=(pagination.page - 1) * pagination.page_size)).mappings().all()
    pagination.has_next = len(rows) > pagination.page_size
    result = rows[:pagination.page_size]
    pagination.displayed = len(result)
    return result


def search_term():
    value = request.args.get('search', '').strip()
    if len(value) > 120:
        abort(400, description='Use at most 120 characters in your search.')
    return value


def like_pattern(value):
    return '%' + value.replace('!', '!!').replace('%', '!%').replace('_', '!_').lower() + '%'
