import importlib
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from lounge_api.public_files import public_path


@pytest.fixture
def public_build(tmp_path, monkeypatch):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "assets").mkdir()
    (root / "index.html").write_text("public shell")
    (root / "public.txt").write_text("public file")
    (root / "assets" / "app.js").write_text("public asset")
    (tmp_path / "outside.txt").write_text("outside marker")
    main = importlib.import_module("lounge_api.main")
    monkeypatch.setattr(main, "web_dist", root)
    return root, main


@pytest.mark.parametrize(
    "path",
    [
        "/..%2Foutside.txt",
        "/%2e%2e/outside.txt",
        "/..%5Coutside.txt",
        "/nested%2F..%2F..%2Foutside.txt",
        "/nested%5C..%5C..%5Coutside.txt",
        "/C:%5Coutside.txt",
        "/public.txt:stream",
        "/assets/..%2F..%2Foutside.txt",
    ],
)
def test_encoded_escape_never_returns_outside_file(public_build, path):
    _, main = public_build
    client = TestClient(main.create_app())
    try:
        response = client.get(path)
        assert response.status_code == 404
        assert "outside marker" not in response.text
    finally:
        client.close()


def test_public_assets_and_game_permalink_still_work(public_build):
    _, main = public_build
    # No lifespan: this test needs no DB, restored games or worker startup.
    client = TestClient(main.create_app())
    try:
        for path, expected in [
            ("/", "public shell"),
            ("/games/id", "public shell"),
            ("/public.txt", "public file"),
            ("/assets/app.js", "public asset"),
        ]:
            response = client.get(path)
            assert response.status_code == 200 and response.text == expected
        assert client.get("/api/unknown").status_code == 404
        assert client.get("/ws/unknown").status_code == 404
    finally:
        client.close()


@pytest.mark.parametrize("link_name", ["leak.txt", "assets/leak.txt", "index.html"])
def test_symlink_escape_is_denied(public_build, link_name):
    root, main = public_build
    link = root / link_name
    if link.exists():
        link.unlink()
    try:
        link.symlink_to(root.parent / "outside.txt")
    except OSError as exc:
        code = getattr(exc, "winerror", exc.errno)
        pytest.skip(f"Host does not permit symlink fixtures: {code}")
    client = TestClient(main.create_app())
    try:
        path = "/games/id" if link_name == "index.html" else f"/{link_name}"
        response = client.get(path)
        assert response.status_code == 404
        assert "outside marker" not in response.text
    finally:
        client.close()


def test_symlink_asset_directory_cannot_be_mounted(public_build):
    root, main = public_build
    (root / "assets" / "app.js").unlink()
    (root / "assets").rmdir()
    try:
        (root / "assets").symlink_to(root.parent, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit directory symlink fixtures")
    with pytest.raises(HTTPException) as error:
        main.create_app()
    assert error.value.status_code == 404


def test_absolute_paths_and_parent_segments_rejected(tmp_path):
    for path in ["/outside", "\\outside", "../outside", "x/../outside", "C:/outside"]:
        with pytest.raises(HTTPException):
            public_path(tmp_path.resolve(), path)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction boundary")
@pytest.mark.parametrize("location", ["jump", "assets/jump"])
def test_windows_directory_junction_escape_is_denied(public_build, location):
    import _winapi

    root, main = public_build
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "marker.txt").write_text("outside marker")
    _winapi.CreateJunction(str(outside), str(root / location))
    client = TestClient(main.create_app())
    try:
        response = client.get(f"/{location}/marker.txt")
        assert response.status_code == 404
        assert "outside marker" not in response.text
    finally:
        client.close()
