"""Browser tests: real Flask templates/JS, intercepted API responses, no live DB writes."""
import json
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from werkzeug.serving import make_server
from app import create_app


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        yield browser
        browser.close()


@pytest.fixture
def ui(browser, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "isolated-browser-test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    app = create_app()
    app.testing = True
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = browser.new_context(viewport={"width":1365,"height":1000})
    page = context.new_page()
    state = SimpleNamespace(posts=[], statuses=["matched"], failure=None, errors=[])
    page.on("pageerror", lambda error: state.errors.append(str(error)))
    deadline = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    def api(route):
        path = route.request.url.split("/api/")[1]
        if state.failure == "catalog" and path == "services":
            route.fulfill(status=503, json={"error":"Catalog offline"}); return
        if path == "services": data = [{"id":7,"name":"Demo Food Support"}]
        elif path == "service-areas": data = [{"id":8,"city":"Calgary","region":"Downtown"}]
        elif path == "priorities": data = [{"id":4,"name":"High","deadline_hours":6}]
        elif route.request.method == "POST":
            state.posts.append(route.request.post_data_json)
            if state.failure == "post":
                route.fulfill(status=400,json={"error":"Invalid service"}); return
            if state.failure == "network": route.abort(); return
            data = {"request_id":42,"status":"submitted","attendance_deadline":deadline}
        else:
            if state.failure == "poll": route.fulfill(status=503,json={"error":"Status offline"}); return
            status = state.statuses.pop(0) if len(state.statuses)>1 else state.statuses[0]
            data = {"request_id":42,"status":status,"service_id":7,"service_area_id":8,
                    "priority_id":4,"attendance_deadline":deadline}
        route.fulfill(json=data)
    page.route("**/api/**", api)
    state.page=page
    state.url=f"http://127.0.0.1:{server.server_port}"
    yield state
    context.close(); server.shutdown(); thread.join(timeout=3); server.server_close()


def open_form(ui):
    ui.page.goto(ui.url+"/demo/request")
    ui.page.locator("#request-fields").wait_for(state="visible")
    ui.page.locator("#service").select_option("7")
    ui.page.locator("#area").select_option("8")
    ui.page.locator("#priority").select_option("4")
    ui.page.locator("#title").fill("Synthetic browser check")
    ui.page.locator("#description").fill("Demo only; no actual assistance requested.")


def test_form_submission_polling_and_duplicate_clicks(ui):
    from playwright.sync_api import expect
    open_form(ui)
    ui.page.locator("#submit-request").evaluate("button => {button.click(); button.click();}")
    expect(ui.page.locator("#submission-receipt")).to_contain_text("Initial status: Submitted")
    expect(ui.page.locator("#status-badge")).to_have_text("Matched",timeout=10000)
    assert len(ui.posts)==1
    assert ui.posts[0]["service_id"]==7 and ui.posts[0]["service_area_id"]==8 and ui.posts[0]["priority_id"]==4
    expect(ui.page.locator("#detail-service")).to_have_text("Demo Food Support")
    expect(ui.page.locator("#detail-deadline")).to_contain_text("local time")
    ui.page.locator("#refresh-status").click()
    ui.page.reload()
    expect(ui.page.locator("#status-badge")).to_have_text("Matched")
    assert len(ui.posts)==1 and not ui.errors


def test_whitespace_validation_does_not_post(ui):
    from playwright.sync_api import expect
    open_form(ui)
    ui.page.locator("#title").fill("   ")
    ui.page.locator("#submit-request").click()
    assert not ui.posts
    assert not ui.page.locator("#title").evaluate("element => element.checkValidity()")
    ui.page.locator("#title").fill("Corrected title")
    ui.page.locator("#submit-request").click()
    expect(ui.page.locator("#detail-id")).to_have_text("#42")


@pytest.mark.parametrize("failure", ["post","network"])
def test_submission_errors_do_not_retry(ui,failure):
    from playwright.sync_api import expect
    open_form(ui); ui.failure=failure
    ui.page.locator("#submit-request").click()
    expect(ui.page.locator("#form-message")).to_be_visible()
    expect(ui.page.locator("#new-request")).to_be_visible()
    assert len(ui.posts)==1
    assert ui.page.locator("#submit-request").is_disabled()
    assert not ui.errors


def test_catalog_failure_and_retry(ui):
    from playwright.sync_api import expect
    ui.failure="catalog"; ui.page.goto(ui.url+"/demo/request")
    expect(ui.page.locator("#form-message")).to_contain_text("Catalog offline")
    assert ui.page.locator("#submit-request").is_disabled()
    ui.failure=None; ui.page.locator("#catalog-retry").click()
    expect(ui.page.locator("#service option")).to_have_count(2)
    expect(ui.page.locator("#submit-request")).to_be_enabled()


def test_unmatched_state_is_reported_honestly(ui):
    from playwright.sync_api import expect
    ui.statuses=["unmatched"]; open_form(ui)
    ui.page.locator("#submit-request").click()
    expect(ui.page.locator("#status-badge")).to_have_text("Unmatched",timeout=10000)
    expect(ui.page.locator("#status-explanation")).to_contain_text("coordinator assistance")
    assert len(ui.posts)==1


def test_polling_failure_keeps_saved_request(ui):
    from playwright.sync_api import expect
    open_form(ui); ui.failure="poll"
    ui.page.locator("#submit-request").click()
    expect(ui.page.locator("#poll-message")).to_contain_text("Status offline",timeout=10000)
    ui.failure=None; ui.page.locator("#refresh-status").click()
    expect(ui.page.locator("#status-badge")).to_have_text("Matched")
    assert len(ui.posts)==1


def test_mobile_layout_and_static_assets(ui):
    ui.page.set_viewport_size({"width":390,"height":844})
    open_form(ui)
    assert ui.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert ui.page.locator("#service").is_visible()
    assert ui.page.request.get(ui.url+"/static/vendor/bootstrap.min.css").status==200
    assert not ui.errors


def test_polling_timeout_stops_without_resubmitting(ui):
    from playwright.sync_api import expect
    ui.statuses=["submitted"]
    ui.page.clock.install()
    open_form(ui)
    ui.page.locator("#submit-request").click()
    expect(ui.page.locator("#detail-id")).to_have_text("#42")
    ui.page.clock.fast_forward(123000)
    expect(ui.page.locator("#poll-message")).to_contain_text("Automatic updates paused")
    ui.statuses=["matched"]
    ui.page.locator("#refresh-status").click()
    expect(ui.page.locator("#status-badge")).to_have_text("Matched")
    assert len(ui.posts)==1
