import json

from lookout.cli import _list_openings
from lookout.config import Settings


def test_list_openings_prints_fields_after_session_closes(session, engine, opening_fixture, capsys):
    opening_id = opening_fixture.id
    session.commit()
    settings = Settings(database_url=engine.url.render_as_string(hide_password=False))

    _list_openings(settings, limit=10)

    output = json.loads(capsys.readouterr().out)
    assert output[0]["id"] == str(opening_id)
    assert output[0]["company"] == "Globex"
    assert output[0]["title"] == "Senior Python Engineer"
