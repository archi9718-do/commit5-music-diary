from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.audio_demo import create_app
from app.db import connect, init_db
from app.import_audio import import_audio
from app.main import app


@pytest.fixture
def catalog(monkeypatch, tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    (root / "local.mp3").write_bytes(b"0123456789")
    (root / "demo.mp3").write_bytes(b"demo")
    (tmp_path / "outside.mp3").write_bytes(b"outside")
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "audio.db"))
    monkeypatch.setenv("MOODWAVE_AUDIO_DIR", str(root))
    init_db()
    with closing(connect()) as con, con:
        con.executemany(
            "INSERT INTO tb_audio VALUES (?, ?, ?, ?, ?)",
            [
                ("custom_001", "Local", "Artist", "local.mp3", 0),
                ("custom_002", "Demo", "Artist", "demo.mp3", 1),
                ("custom_003", "Missing", "Artist", "missing.mp3", 1),
                ("custom_004", "Outside", "Artist", "../outside.mp3", 1),
                ("custom_005", "Absolute", "Artist", (root / "local.mp3").as_posix(), 1),
            ],
        )


def test_local_list_and_seek_response(catalog):
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 10000))
    tracks = client.get("/api/audio").json()["tracks"]
    assert [track["audio_id"] for track in tracks] == ["custom_001", "custom_002"]
    assert set(tracks[0]) == {"audio_id", "title", "artist", "audio_url"}
    url = tracks[0]["audio_url"]
    response = client.get(url, headers={"Range": "bytes=2-5"})
    assert response.status_code == 206
    assert response.headers["Content-Type"] == "audio/mpeg"
    assert response.headers["Content-Range"] == "bytes 2-5/10"
    assert response.content == b"2345"
    assert client.head(url).headers["Content-Length"] == "10"


def test_remote_can_only_stream_approved_existing_mp3_files(catalog):
    client = TestClient(app, base_url="http://localhost", client=("192.168.0.10", 10000))
    assert [track["audio_id"] for track in client.get("/api/audio").json()["tracks"]] == ["custom_002"]
    for track in ("custom_001", "custom_003", "custom_004", "custom_005", "custom_999"):
        assert client.get(f"/api/audio/{track}").status_code == 404
    response = client.get("/api/audio/custom_002")
    assert response.status_code == 200
    assert response.content == b"demo"
    assert TestClient(app, client=("127.0.0.1", 10000)).get("/api/audio/custom_001").status_code == 404


def test_demo_server_only_offers_approved_audio_and_player(catalog, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "test.js").write_text("// js", encoding="utf-8")
    (dist / "index.html").write_text("Audio demo", encoding="utf-8")
    (dist / "server-config.json").write_text("private", encoding="utf-8")
    client = TestClient(create_app(dist), base_url="http://localhost", client=("127.0.0.1", 10000))
    assert client.get("/").text == "Audio demo"
    assert [track["audio_id"] for track in client.get("/api/audio").json()["tracks"]] == ["custom_002"]
    assert client.get("/api/audio/custom_001").status_code == 404
    assert client.get("/api/records/1/lp").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/assets/test.js").status_code == 200
    assert client.get("/server-config.json").status_code == 404


def test_first_start_creates_only_audio_table(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "new.db"))
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("Audio demo", encoding="utf-8")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/audio").json() == {"tracks": []}
    with closing(connect()) as con:
        assert [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")] == ["tb_audio"]


def test_import_updates_catalog_without_creating_diary_tables(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "new.db"))
    (tmp_path / "song.mp3").write_bytes(b"demo")
    manifest = tmp_path / "tracks.csv"
    header = "song_id,title,artist,filename,is_public_demo\n"
    manifest.write_text(header + "custom_001,Song,Artist,song.mp3,0\n", encoding="utf-8")
    assert import_audio(manifest, tmp_path) == 1
    manifest.write_text(header + "custom_001,Song,Artist,song.mp3,1\n", encoding="utf-8")
    assert import_audio(manifest, tmp_path) == 1
    with closing(connect()) as con:
        assert [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")] == ["tb_audio"]
        assert [row[0] for row in con.execute("SELECT is_public_demo FROM tb_audio")] == [1]
