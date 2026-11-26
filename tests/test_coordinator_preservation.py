"""All 250 synthetic requests stay accessible after filtering and pagination."""
from datetime import date, timedelta
import html
import re

import pytest
from flask import template_rendered
from sqlalchemy import text

from app import db
from test_list_queries import listing_app, signed_client


def row_ids(response):
    assert response.status_code == 200
    return [int(value) for value in re.findall(r'<tr id="request-([0-9]+)"', response.get_data(as_text=True))]


@pytest.fixture
def large_app(listing_app):
    with listing_app.app_context(), db.engine.begin() as connection:
        for number in range(51, 251):
            status = {0: 'completed', 1: 'unmatched', 2: 'submitted', 3: 'matched'}[number % 4]
            description = 'audit request ' + str(number)
            if number == 249:
                description = 'A late-page needle'
            if number == 248:
                description = 'Literal needle_%! record'
            connection.execute(text('''INSERT INTO service_requests
                (request_id,member_id,service_id,priority_id,status,created_at,description,attendance_deadline)
                VALUES(:id,:owner,:service,:priority,:status,:created,:description,'2030-01-01')'''), {
                'id': number, 'owner': 1 if number <= 245 else 4, 'service': 1 + number % 2,
                'priority': 1 + number % 3, 'status': status,
                'created': (date(2026, 1, 1) + timedelta(days=number % 28)).isoformat(), 'description': description,
            })
            if number % 12 == 0:
                connection.execute(text("INSERT INTO referrals VALUES(:id,:id,2,'completed',1,'2030-01-01')"), {'id': number})
                connection.execute(text('INSERT INTO feedback VALUES(:id,:id,FALSE)'), {'id': number})
        connection.execute(text("INSERT INTO referrals VALUES(61,61,2,'rejected',1,'2030-01-01'),(62,62,2,'timed_out',1,'2030-01-01')"))
        connection.execute(text("UPDATE service_requests SET status='submitted' WHERE request_id IN (61,62)"))
        connection.execute(text("UPDATE service_requests SET attendance_deadline='2020-01-01' WHERE request_id=63"))
        # Three coherent attempts and history entries for one existing request.
        connection.execute(text("UPDATE referrals SET status='rejected' WHERE referral_id=7"))
        connection.execute(text("INSERT INTO referrals VALUES(251,7,2,'rejected',2,'2030-01-01'),(252,7,1,'accepted',3,'2030-01-01')"))
        connection.execute(text("INSERT INTO referral_status_history VALUES(1,7,'sent','2026-01-01'),(2,251,'rejected','2026-01-02'),(3,252,'accepted','2026-01-03')"))
    return listing_app


def test_all_250_requests_are_reachable_across_thirteen_default_pages(large_app):
    client = signed_client(large_app, 'coordinator')
    seen = []
    for page in range(1, 14):
        response = client.get('/coordinator/requests', query_string={'page': page})
        ids = row_ids(response)
        assert len(ids) == (20 if page < 13 else 10)
        assert (b'rel="next"' in response.data) == (page < 13)
        assert (b'rel="prev"' in response.data) == (page > 1)
        seen.extend(ids)
    assert len(seen) == len(set(seen)) == 250
    assert set(seen) == set(range(1, 251))


@pytest.mark.parametrize('sort,order', [('oldest', 'ASC'), ('newest', 'DESC')])
def test_date_sort_applies_to_all_250_requests_not_just_page_one(large_app, sort, order):
    client = signed_client(large_app, 'coordinator')
    actual = []
    for page in range(1, 6):
        actual.extend(row_ids(client.get('/coordinator/requests', query_string={'page': page, 'page_size': 50, 'sort': sort})))
    with large_app.app_context(), db.engine.connect() as connection:
        rows = connection.execute(text('SELECT request_id,created_at FROM service_requests')).all()
    expected = [row.request_id for row in sorted(rows, key=lambda row: (row.created_at, row.request_id), reverse=order == 'DESC')]
    assert actual == expected


@pytest.mark.parametrize('query,expected', [
    ('CC-249', [249]), ('late-page needle', [249]), ('needle_%!', [248]),
    ('Partner Two', None),
])
def test_search_is_parameterized_and_reaches_late_page_records(large_app, query, expected):
    client = signed_client(large_app, 'coordinator')
    response = client.get('/coordinator/requests', query_string={'search': query, 'page_size': 50})
    actual = row_ids(response)
    if query == 'Partner Two':
        # Existing and new referred requests across the dataset, not a page subset.
        with large_app.app_context(), db.engine.connect() as connection:
            wanted = set(connection.execute(text('''SELECT request_id FROM referrals WHERE organization_id=2
                AND request_id<>7''')).scalars())
        assert set(actual) == wanted
    else:
        assert actual == expected
    assert 'search=' in html.unescape(response.get_data(as_text=True))


def test_combined_original_filters_are_applied_before_pagination_and_clear_restores_list(large_app):
    client = signed_client(large_app, 'coordinator')
    filters = dict(status='Completed', priority='High', org_id='2', attention='Manual review', page_size=10, sort='oldest')
    first = client.get('/coordinator/requests', query_string=filters)
    second = client.get('/coordinator/requests', query_string=dict(filters, page=2))
    ids = row_ids(first) + row_ids(second)
    assert set(ids) == set(range(60, 241, 12)) and len(ids) == 16
    assert len(row_ids(first)) == 10 and len(row_ids(second)) == 6
    content = html.unescape(first.get_data(as_text=True))
    for part in ['status=Completed', 'priority=High', 'org_id=2', 'attention=Manual+review', 'page=2']:
        assert part in content
    assert len(row_ids(client.get('/coordinator/requests'))) == 20
    assert client.get('/coordinator/requests?page=13').status_code == 200


@pytest.mark.parametrize('attention,expected', [('Rejected referral', 61), ('Expired referral', 62), ('Overdue', 63), ('Unmatched', 65)])
def test_all_original_attention_filters_remain_available(large_app, attention, expected):
    client = signed_client(large_app, 'coordinator')
    ids = []
    for page in (1, 2):
        ids.extend(row_ids(client.get('/coordinator/requests', query_string={'attention': attention, 'page_size': 50, 'page': page})))
    assert expected in ids


def test_search_validation_empty_results_and_injection_do_not_change_scope(large_app):
    client = signed_client(large_app, 'coordinator')
    assert row_ids(client.get('/coordinator/requests', query_string={'search': "' OR 1=1 --"})) == []
    assert row_ids(client.get('/coordinator/requests', query_string={'search': 'does-not-exist'})) == []
    assert client.get('/coordinator/requests', query_string={'search': 'x' * 121}).status_code == 400


@pytest.mark.parametrize('role', ['member', 'organization'])
def test_search_does_not_bypass_coordinator_authorization(large_app, role):
    response = signed_client(large_app, role).get('/coordinator/requests?search=person@example.test')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_dashboard_and_report_totals_are_global_and_detail_preserves_all_referral_history(large_app):
    client = signed_client(large_app, 'coordinator')
    contexts = []
    def capture(sender, template, context, **extra):
        contexts.append(context)
    with template_rendered.connected_to(capture, large_app):
        assert client.get('/coordinator?page=13').status_code == 200
        assert contexts[-1]['counts']['total'] == 250
        assert len(contexts[-1]['attention_requests']) <= 5
        assert client.get('/coordinator/reports?page=13').status_code == 200
        assert contexts[-1]['totals']['requests'] == 250
    detail = client.get('/coordinator/requests/7?search=CC-7&page=3&sort=oldest')
    assert detail.status_code == 200
    assert b'Referral sent' in detail.data and b'Referral declined' in detail.data and b'Referral accepted' in detail.data
    assert 'search=CC-7' in html.unescape(detail.get_data(as_text=True))
