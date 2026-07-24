from __future__ import annotations

import requests


def session() -> requests.Session:
    value = requests.Session()
    value.headers.update(
        {
            "User-Agent": "ResearchRadar/0.1 (+https://github.com/RayeRuixinZhang/Research-Radar; mailto:zrxzrx1227@163.com)",
            "Accept": "application/json, application/xml, text/xml, application/rss+xml, */*",
        }
    )
    return value


def get_json(url: str, params: dict | None = None, timeout: int = 45) -> dict:
    response = session().get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()

