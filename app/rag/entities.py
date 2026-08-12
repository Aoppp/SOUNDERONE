from __future__ import annotations

import re
from dataclasses import dataclass


DOSAGE_SUFFIX_RE = re.compile(
    r"(?:精华液|精华乳|精华油|精华|面霜|乳霜|眼霜|洗发水|护发素)$",
    re.IGNORECASE,
)
NORMALIZE_RE = re.compile(r"[\s\n\r\t（）()·_—-]+")


@dataclass(frozen=True)
class ProductMatch:
    canonical_name: str
    matched_alias: str


class ProductEntityResolver:
    """Normalize product names, customer nicknames and abbreviations."""

    CURATED_ALIASES = {
        "am": "AM洗发水",
        "am洗发水": "AM洗发水",
        "氨基酸洗发水": "AM洗发水",
        "vcip": "30%VCIP光感清透精华油",
        "vcip精华": "30%VCIP光感清透精华油",
        "vcip精华油": "30%VCIP光感清透精华油",
        "30%vcip": "30%VCIP光感清透精华油",
        "b5洗发水": "B5洗发水",
        "b5": "B5洗发水",
        "夜猫子": "夜猫子精华",
        "euk": "EUK-134精华",
        "euk134": "EUK-134精华",
        "euk-134": "EUK-134精华",
        "双a醇": "双A醇眼霜",
        "木洗发水": "净澈控油沁爽洗发水（木）",
        "火洗发水": "蓬松丰盈洗发水（火）",
        "水洗发水": "神经酰胺头皮专护洗发水（水）",
        "土洗发水": "二硫化硒去屑洗发水（土）",
    }

    def __init__(self, aliases: set[str]):
        mapping: dict[str, str] = {}
        for alias in aliases:
            cleaned = self._display(alias)
            if not cleaned or len(self.normalize(cleaned)) < 2:
                continue
            mapping[self.normalize(cleaned)] = cleaned
            shorthand = DOSAGE_SUFFIX_RE.sub("", cleaned)
            if len(self.normalize(shorthand)) >= 3:
                mapping.setdefault(self.normalize(shorthand), cleaned)
        for alias, canonical in self.CURATED_ALIASES.items():
            mapping[self.normalize(alias)] = canonical
        self.alias_to_canonical = mapping

    @staticmethod
    def _display(value: str) -> str:
        return re.sub(r"\s+", "", value).strip("（）() ")

    @staticmethod
    def normalize(value: str) -> str:
        return NORMALIZE_RE.sub("", value).lower()

    def find_all(self, text: str) -> list[ProductMatch]:
        normalized = self.normalize(text)
        matches = [
            ProductMatch(canonical, alias)
            for alias, canonical in self.alias_to_canonical.items()
            if alias and alias in normalized
        ]
        matches.sort(key=lambda item: len(item.matched_alias), reverse=True)
        selected: list[ProductMatch] = []
        seen: set[str] = set()
        for match in matches:
            if match.canonical_name not in seen:
                selected.append(match)
                seen.add(match.canonical_name)
        return selected

    def identify(self, text: str) -> str:
        matches = self.find_all(text)
        return matches[0].canonical_name if matches else ""

    def entities(self, text: str) -> set[str]:
        return {match.canonical_name for match in self.find_all(text)}
