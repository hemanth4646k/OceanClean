import json

import pytest
from fetch_microplastics import bronze_document, fetch_features, page_params
from oceanclean_common.regions import HISTORY_BOX


def feature(oid: int) -> dict[str, object]:
    return {"attributes": {"OBJECTID": oid}, "geometry": {"x": -140.0, "y": 32.0}}


def fake_server(total: int, page_size: int) -> tuple[list[dict[str, str]], object]:
    calls: list[dict[str, str]] = []

    def get_json(params: dict[str, str]) -> dict[str, object]:
        calls.append(params)
        if params.get("returnCountOnly") == "true":
            return {"count": total}
        off = int(params["resultOffset"])
        rows = [feature(i) for i in range(off, min(off + page_size, total))]
        return {"features": rows, "exceededTransferLimit": off + page_size < total}

    return calls, get_json


def test_page_params_query_the_gyre_envelope_in_wgs84() -> None:
    p = page_params(2000, HISTORY_BOX)
    assert p["geometry"] == "-180.0,20.0,-130.0,45.0"
    assert p["geometryType"] == "esriGeometryEnvelope"
    assert p["inSR"] == "4326"
    assert p["resultOffset"] == "2000"
    assert p["orderByFields"] == "OBJECTID"
    assert p["f"] == "json"


def test_fetch_features_pages_until_the_server_says_done() -> None:
    calls, get_json = fake_server(total=4500, page_size=2000)
    feats = fetch_features(get_json, HISTORY_BOX)
    assert [f["attributes"]["OBJECTID"] for f in feats] == list(range(4500))
    offsets = [c["resultOffset"] for c in calls if "resultOffset" in c]
    assert offsets == ["0", "2000", "4000"]


def test_fetch_features_fails_when_paging_misses_records() -> None:
    _, get_json = fake_server(total=10, page_size=4)

    def lossy(params: dict[str, str]) -> dict[str, object]:
        page = get_json(params)
        if params.get("resultOffset") == "4":  # server stops early with a short page
            page["features"] = page["features"][:1]
            page["exceededTransferLimit"] = False
        return page

    with pytest.raises(ValueError, match="expected 10"):
        fetch_features(lossy, HISTORY_BOX)


def test_fetch_features_surfaces_arcgis_errors() -> None:
    def broken(params: dict[str, str]) -> dict[str, object]:
        return {"error": {"code": 400, "message": "Invalid query"}}

    with pytest.raises(ValueError, match="Invalid query"):
        fetch_features(broken, HISTORY_BOX)


def test_bronze_document_keeps_raw_features_and_fetch_time() -> None:
    doc = json.loads(bronze_document([feature(1)], "2026-10-31T12:00:00+00:00"))
    assert doc["fetched_at"] == "2026-10-31T12:00:00+00:00"
    assert doc["features"] == [feature(1)]
    assert doc["query_url"].endswith("/FeatureServer/0/query")
