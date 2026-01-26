from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class ParsedItem:
    source: str
    external_id: str
    url: str
    title: str = ""
    price: int | None = None
    published_at: str | None = None
    raw: Any | None = None


_SCRIPT_LD_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

# Паттерн для поиска items в Avito JSON
_AVITO_ITEM_RE = re.compile(
    r'\{"id":(\d+),[^}]*?"urlPath":"([^"]+)"[^}]*?"title":"([^"]*)"',
    re.DOTALL,
)

# Паттерн для поиска цены в Avito (формат: "string":"30 750")
_AVITO_PRICE_RE = re.compile(r'"priceDetailed":\{[^}]*"string":"([\d\s]+)"')


def _is_avito_url(url: str) -> bool:
    """Проверяет, является ли URL ссылкой на Avito."""
    try:
        host = urlparse(url).netloc.lower()
        return "avito.ru" in host
    except Exception:
        return False


def _parse_avito(base_url: str, text: str, max_items: int = 50) -> tuple[list[dict], str | None]:
    """Парсит страницу Avito.

    Возвращает (items, redirect_url).
    Если redirect_url не None, нужно загрузить эту страницу.
    """
    # Декодируем HTML entities
    text_decoded = html.unescape(text)

    # Проверяем наличие redirect
    redirect_match = re.search(r'"redirect":"(/[^"]+)"', text_decoded)
    if redirect_match:
        redirect_path = redirect_match.group(1)
        # Убираем возможные escape-последовательности
        redirect_path = redirect_path.replace("\\u0026", "&").replace("\\/", "/")
        redirect_url = f"https://www.avito.ru{redirect_path}"
        return [], redirect_url

    # Ищем items в JSON
    items: list[dict] = []
    seen_ids: set[str] = set()

    # Ищем все совпадения item
    for match in _AVITO_ITEM_RE.finditer(text_decoded):
        item_id = match.group(1)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        url_path = match.group(2)
        title = match.group(3)

        # Убираем escape-последовательности из title (но не трогаем UTF-8)
        title = title.replace("\\/", "/")

        # Формируем полный URL
        # URL path может содержать context параметр, берём только основную часть
        clean_path = url_path.split("?")[0]
        if not clean_path.startswith("/"):
            clean_path = "/" + clean_path
        full_url = f"https://www.avito.ru{clean_path}"

        # Ищем цену рядом с этим item
        # Ищем в окрестности 2000 символов после id (priceDetailed может быть далеко)
        start_pos = match.start()
        search_region = text_decoded[start_pos:start_pos + 2000]
        price_match = _AVITO_PRICE_RE.search(search_region)
        price = None
        if price_match:
            # Цена в формате "30 750" - убираем пробелы
            price_str = price_match.group(1).replace(" ", "").replace("\u00a0", "")
            if price_str.isdigit():
                price = int(price_str)

        items.append({
            "source": "avito",
            "external_id": item_id,
            "url": full_url,
            "title": title,
            "price": price,
            "published_at": None,
            "raw": {"id": item_id, "urlPath": url_path, "title": title},
        })

        if len(items) >= max_items:
            break

    return items, None


def _hostname(source_url: str) -> str:
    try:
        return urlparse(source_url).netloc.lower() or "generic"
    except Exception:
        return "generic"


def _normalize_url(base_url: str, maybe_url: str) -> str:
    maybe_url = (maybe_url or "").strip()
    if not maybe_url:
        return ""
    return urljoin(base_url, maybe_url)


def _external_id_from_url(u: str) -> str:
    try:
        parsed = urlparse(u)
        path = (parsed.path or "").strip("/")
        if path:
            last = path.split("/")[-1]
            # частый кейс: числовой id в конце
            digits = re.sub(r"\D+", "", last)
            if digits:
                return digits
        # fallback: хеш всей ссылки
        return hashlib.md5(u.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    except Exception:
        return hashlib.md5(u.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _to_int_price(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"\D+", "", value)
        return int(digits) if digits else None
    return None


def _parse_datetime_iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        # unix timestamp
        try:
            return datetime.utcfromtimestamp(float(value)).replace(microsecond=0).isoformat() + "Z"
        except Exception:
            return None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        # Python не парсит 'Z' напрямую через fromisoformat
        if v.endswith("Z"):
            v2 = v[:-1] + "+00:00"
        else:
            v2 = v
        try:
            dt = datetime.fromisoformat(v2)
            # сериализуем обратно в ISO
            if dt.tzinfo is None:
                return dt.replace(microsecond=0).isoformat() + "Z"
            return dt.replace(microsecond=0).isoformat()
        except Exception:
            return None
    return None


def _iter_json_objects(obj: Any):
    if obj is None:
        return
    if isinstance(obj, list):
        for x in obj:
            yield from _iter_json_objects(x)
        return
    if isinstance(obj, dict):
        yield obj
        # часто встречается @graph
        if "@graph" in obj:
            yield from _iter_json_objects(obj.get("@graph"))
        return


def _extract_from_jsonld(base_url: str, jsonld_obj: Any) -> list[ParsedItem]:
    out: list[ParsedItem] = []
    source = _hostname(base_url)

    for o in _iter_json_objects(jsonld_obj):
        t = o.get("@type")
        if isinstance(t, list):
            # бывает несколько типов
            t = t[0] if t else None

        if t == "ItemList":
            elements = o.get("itemListElement") or []
            if isinstance(elements, dict):
                elements = [elements]
            if not isinstance(elements, list):
                continue
            for el in elements:
                if not isinstance(el, dict):
                    continue
                item_obj = el.get("item") if isinstance(el.get("item"), dict) else el
                url_val = item_obj.get("url") or item_obj.get("@id") or ""
                url_norm = _normalize_url(base_url, str(url_val))
                if not url_norm:
                    continue
                title = str(item_obj.get("name") or item_obj.get("title") or "").strip()

                offers = item_obj.get("offers") if isinstance(item_obj, dict) else None
                price = None
                if isinstance(offers, dict):
                    price = _to_int_price(offers.get("price"))
                published_at = _parse_datetime_iso(item_obj.get("datePublished") or item_obj.get("dateCreated"))

                out.append(
                    ParsedItem(
                        source=source,
                        external_id=_external_id_from_url(url_norm),
                        url=url_norm,
                        title=title,
                        price=price,
                        published_at=published_at,
                        raw=item_obj,
                    )
                )

        if t == "Product":
            url_val = o.get("url") or o.get("@id") or ""
            url_norm = _normalize_url(base_url, str(url_val))
            if not url_norm:
                continue
            title = str(o.get("name") or "").strip()
            offers = o.get("offers")
            price = None
            if isinstance(offers, dict):
                price = _to_int_price(offers.get("price"))
            published_at = _parse_datetime_iso(o.get("datePublished") or o.get("dateCreated"))
            out.append(
                ParsedItem(
                    source=source,
                    external_id=_external_id_from_url(url_norm),
                    url=url_norm,
                    title=title,
                    price=price,
                    published_at=published_at,
                    raw=o,
                )
            )

    # дедуп по URL
    uniq: dict[str, ParsedItem] = {}
    for item in out:
        if item.url and item.url not in uniq:
            uniq[item.url] = item
    return list(uniq.values())


def parse_items(
    base_url: str,
    *,
    content_type: str | None,
    text: str,
    max_items: int = 50,
) -> list[dict] | tuple[list[dict], str | None]:
    """Пытается извлечь объявления из ответа.

    Без "обходов": только стандартные источники данных в ответе (JSON/JSON-LD).
    Возвращает список словарей под контракт backend/api/serializers.WorkerItemIn.

    Для Avito может вернуть tuple (items, redirect_url) если нужен redirect.
    """

    ct = (content_type or "").lower()
    src = _hostname(base_url)

    # Специальная обработка для Avito
    if _is_avito_url(base_url):
        items, redirect_url = _parse_avito(base_url, text, max_items)
        if redirect_url:
            # Возвращаем tuple с redirect URL
            return items, redirect_url
        if items:
            return items
        # Если items пустой, пробуем стандартные методы ниже

    # 1) JSON ответ
    if "application/json" in ct or text.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(text)
        except Exception:
            data = None

        items: list[dict] = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            # частые кейсы: {items:[...]}, {data:{items:[...]}}
            candidates = (
                data.get("items")
                or (data.get("data") or {}).get("items")
                or (data.get("result") or {}).get("items")
                or []
            )
        else:
            candidates = []

        if isinstance(candidates, dict):
            candidates = [candidates]

        if isinstance(candidates, list):
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                url_val = c.get("url") or c.get("link") or ""
                url_norm = _normalize_url(base_url, str(url_val))
                if not url_norm:
                    continue
                external_id = str(c.get("id") or c.get("external_id") or _external_id_from_url(url_norm))
                title = str(c.get("title") or c.get("name") or "").strip()
                price = _to_int_price(c.get("price"))
                published_at = _parse_datetime_iso(c.get("published_at") or c.get("published") or c.get("date"))
                items.append(
                    {
                        "source": src,
                        "external_id": external_id,
                        "url": url_norm,
                        "title": title,
                        "price": price,
                        "published_at": published_at,
                        "raw": c,
                    }
                )
        return items[:max_items]

    # 2) HTML: JSON-LD
    parsed: list[ParsedItem] = []
    for m in _SCRIPT_LD_JSON_RE.finditer(text):
        body = html.unescape(m.group("body") or "").strip()
        if not body:
            continue
        try:
            obj = json.loads(body)
        except Exception:
            continue
        parsed.extend(_extract_from_jsonld(base_url, obj))

    items_out: list[dict] = []
    for p in parsed[:max_items]:
        items_out.append(
            {
                "source": p.source or src,
                "external_id": p.external_id,
                "url": p.url,
                "title": p.title or "",
                "price": p.price,
                "published_at": p.published_at,
                "raw": p.raw,
            }
        )

    return items_out
