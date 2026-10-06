"""Event deletion preserves history and hides cancelled events."""
import uuid


def _event(cursor, chapter_id):
    cursor.execute("INSERT INTO events (chapter_id,title,date,time,location,required) VALUES (%s,'Delete test','2026-07-01','19:00','Hall',true) RETURNING id", (chapter_id,))
    return str(cursor.fetchone()['id'])


def _delete(as_member, actor, event_id):
    response = as_member(actor['id']).delete(f'/api/events/{event_id}')
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_event_is_deleted(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    # Expired, inactive links and assignment rows are not history.
    cursor.execute("INSERT INTO checkin_links(event_id,short_code,expires_at,active) VALUES (%s,%s,now()-interval '1 day',false)", (event_id, uuid.uuid4().hex))
    assert _delete(as_member, actor, event_id) == {'deleted': True, 'cancelled': False}
    cursor.execute('SELECT id FROM events WHERE id=%s', (event_id,))
    assert cursor.fetchone() is None


def test_event_with_attendance_is_cancelled_not_deleted(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    cursor.execute('INSERT INTO attendance(event_id,member_id) VALUES (%s,%s) RETURNING id', (event_id, actor['id']))
    attendance_id = cursor.fetchone()['id']
    assert _delete(as_member, actor, event_id) == {'deleted': False, 'cancelled': True}
    cursor.execute('SELECT cancelled,required FROM events WHERE id=%s', (event_id,))
    assert dict(cursor.fetchone()) == {'cancelled': True, 'required': False}
    cursor.execute('SELECT id FROM attendance WHERE id=%s', (attendance_id,))
    assert cursor.fetchone()


def test_cancel_closes_open_work(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    cursor.execute("INSERT INTO checkin_links(event_id,short_code,expires_at) VALUES (%s,%s,now()+interval '1 day')", (event_id, uuid.uuid4().hex))
    cursor.execute("INSERT INTO tasks(chapter_id,event_id,title) VALUES (%s,%s,'Job') RETURNING id", (chapter_id,event_id))
    task_id = cursor.fetchone()['id']
    cursor.execute("INSERT INTO unpaid_invoices(chapter_id,member_id,source_event_id,kind,amount_cents,description) VALUES (%s,%s,%s,'fine',100,'Fine') RETURNING id", (chapter_id,actor['id'],event_id))
    invoice_id = cursor.fetchone()['id']
    cursor.execute('SELECT * FROM unpaid_invoices WHERE id=%s', (invoice_id,))
    invoice = dict(cursor.fetchone())
    assert _delete(as_member, actor, event_id)['cancelled']
    cursor.execute('SELECT active FROM checkin_links WHERE event_id=%s', (event_id,))
    assert not cursor.fetchone()['active']
    cursor.execute('SELECT status FROM tasks WHERE id=%s', (task_id,))
    assert cursor.fetchone()['status'] == 'cancelled'
    cursor.execute('SELECT * FROM unpaid_invoices WHERE id=%s', (invoice_id,))
    assert dict(cursor.fetchone()) == invoice


def test_cancelled_event_is_hidden_from_lists(cursor, chapter_id, user_factory, as_member, sb_client, monkeypatch):
    import api.calendar.api.calendar as calendar_api
    monkeypatch.setattr(calendar_api, 'get_db', lambda: sb_client)
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    cursor.execute("INSERT INTO tasks(chapter_id,event_id,title) VALUES (%s,%s,'Job')", (chapter_id,event_id))
    _delete(as_member, actor, event_id)
    for user in (actor, user_factory()):
        client = as_member(user['id'])
        assert event_id not in {e['id'] for e in client.get('/api/events/').json()}
        response = client.get('/api/calendar', params={'start':'2026-07-01','end':'2026-07-02'})
        assert response.status_code == 200, response.text
        assert event_id not in str(response.json())
        assert client.get(f'/api/events/{event_id}').status_code == 404


def test_cancel_writes_audit_row(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    cursor.execute("INSERT INTO tasks(chapter_id,event_id,title) VALUES (%s,%s,'Job')", (chapter_id,event_id))
    _delete(as_member, actor, event_id)
    cursor.execute("SELECT metadata FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='UPDATE_EVENT'", (chapter_id,event_id))
    assert [r['metadata'] for r in cursor.fetchall()] == [{'cancelled': True}]


def test_delete_other_chapter_is_404(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    cursor.execute("INSERT INTO chapters(name,organization,school) VALUES ('Other delete chapter','Test','Test') RETURNING id")
    event_id = _event(cursor, str(cursor.fetchone()['id']))
    assert as_member(actor['id']).delete(f'/api/events/{event_id}').status_code == 404
    cursor.execute('SELECT id FROM events WHERE id=%s', (event_id,))
    assert cursor.fetchone()


def test_cancelling_twice_is_a_noop_success(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    cursor.execute("INSERT INTO tasks(chapter_id,event_id,title) VALUES (%s,%s,'Job')", (chapter_id,event_id))
    assert _delete(as_member, actor, event_id) == _delete(as_member, actor, event_id) == {'deleted': False, 'cancelled': True}
    cursor.execute("SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='UPDATE_EVENT'", (chapter_id,event_id))
    assert cursor.fetchone()['n'] == 1


def test_cancelled_event_cannot_be_edited(cursor, chapter_id, user_factory, as_member):
    actor = user_factory(role='officer')
    event_id = _event(cursor, chapter_id)
    cursor.execute('INSERT INTO attendance(event_id,member_id) VALUES (%s,%s)', (event_id, actor['id']))
    assert _delete(as_member, actor, event_id)['cancelled']
    response = as_member(actor['id']).put(f'/api/events/{event_id}', json={'title': 'Revived'})
    assert response.status_code == 404, response.text
