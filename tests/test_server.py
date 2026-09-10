from fastapi.testclient import TestClient

from pricewatch.server import make_app


def test_server_health_and_dashboard(tmp_path):
    db_file = tmp_path / "test.db"
    app = make_app(str(db_file))
    client = TestClient(app)

    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["ok"] is True

    r_obs = client.get("/observations")
    assert r_obs.status_code == 200
    assert isinstance(r_obs.json(), list)

    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "PriceWatch" in r_dash.text
    assert "Products Tracked" in r_dash.text
