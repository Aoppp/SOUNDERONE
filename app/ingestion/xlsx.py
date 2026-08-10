from __future__ import annotations

import hashlib
import json
import math
import posixpath
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "pr": PACKAGE_REL_NS}

CANONICAL_PRODUCT_SHEET = "三蛋丸"
LEGACY_PRODUCT_SHEET = "三蛋丸产品介绍"
FAQ_SHEETS = {
    "话术汇总": ("A", ("B", "C", "D", "E")),
    "运营话术": ("A", ("B", "C", "D", "E")),
    "三蛋丸微信群QA记录": ("A", ("B",)),
    "京东问答": ("A", ("B",)),
}
ORDER_HEADERS = {"订单号", "订单明细-正装", "实付金额", "负责人"}

HAIR_PRODUCT_NAMES = {
    "金\n护发素": "SOUNDER ONE 柔润亮泽护发素",
    "木": "SOUNDER ONE 净澈控油沁爽洗发水",
    "水": "SOUNDER ONE 神经酰胺头皮专护洗发水",
    "火": "SOUNDER ONE 蓬松丰盈洗发水",
    "土": "SOUNDER ONE 二硫化硒去屑洗发水",
}

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_RE = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{15,}(?!\d)")
PERCENT_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*%")
ADDRESS_RE = re.compile(r"(?:省|市|区|县|街道|路|号).{0,100}(?:仓库|收货人|收件人)")

HANDOFF_RULES = {
    "adverse_reaction": ("过敏", "红肿", "刺痛", "烂脸", "起疹", "不良反应", "头皮发痒", "头皮会痒"),
    "complex_after_sales": (
        "退款",
        "退货",
        "退差价",
        "补发",
        "漏发",
        "少发",
        "修改地址",
        "拦截包裹",
        "赔偿",
        "售后",
        "赠品未退",
        "小样未退",
        "少退回",
        "少寄回",
        "退差价",
        "扣款",
        "价保",
    ),
    "legal_or_media": ("律师", "起诉", "媒体", "曝光", "市场监管", "消协"),
}
REVIEW_RULES = {
    "pregnancy_conflict": ("孕妇", "孕妈妈", "孕妈", "怀孕", "孕期", "哺乳"),
    "medical_or_procedure": ("医嘱", "医生", "医院", "医美", "光电项目", "临床", "诊断", "药品"),
    "unsafe_reassurance": (
        "忍一忍",
        "坚持使用",
        "一定会",
        "一定是会",
        "不可能会",
        "假性过敏",
        "完全安心",
        "100%",
        "百分百",
        "保证有效",
    ),
    "regulated_claim": ("治疗", "治愈", "抗炎", "消炎", "防脱", "生发", "杀菌", "抑制马拉色菌"),
    "minor_usage": ("儿童", "未成年", "13岁", "6岁以上"),
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalize_text(value).lower())


def column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        raise ValueError(f"invalid cell reference: {reference}")
    result = 0
    for char in letters.group():
        result = result * 26 + ord(char) - 64
    return result


def column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def split_reference(reference: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", reference)
    if not match:
        raise ValueError(f"invalid cell reference: {reference}")
    return match.group(1), int(match.group(2))


@dataclass(frozen=True)
class Sheet:
    name: str
    rows: tuple[dict[str, str], ...]
    merged_ranges: tuple[str, ...]

    @property
    def header(self) -> set[str]:
        if not self.rows:
            return set()
        return {normalize_text(value) for key, value in self.rows[0].items() if key != "_row" and value}


class XlsxWorkbook:
    """Minimal OOXML reader for deterministic, dependency-free ingestion."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> tuple[list[Sheet], int]:
        with zipfile.ZipFile(self.path) as archive:
            shared_strings = self._shared_strings(archive)
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}
            sheets: list[Sheet] = []
            for element in workbook.find("m:sheets", NS) or []:
                relationship_id = element.attrib[f"{{{REL_NS}}}id"]
                target = targets[relationship_id].lstrip("/")
                if not target.startswith("xl/"):
                    target = posixpath.normpath(posixpath.join("xl", target))
                sheets.append(self._sheet(archive, target, element.attrib["name"], shared_strings))
            image_count = sum(name.startswith("xl/media/") for name in archive.namelist())
            return sheets, image_count

    @staticmethod
    def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        return [
            "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
            for item in root.findall("m:si", NS)
        ]

    @staticmethod
    def _sheet(
        archive: zipfile.ZipFile, target: str, name: str, shared_strings: list[str]
    ) -> Sheet:
        root = ET.fromstring(archive.read(target))
        row_map: dict[int, dict[str, str]] = {}
        for row in root.findall(".//m:sheetData/m:row", NS):
            row_number = int(row.attrib["r"])
            values: dict[str, str] = {"_row": str(row_number)}
            for cell in row.findall("m:c", NS):
                reference = cell.attrib.get("r", "")
                column, _ = split_reference(reference)
                cell_type = cell.attrib.get("t")
                value_node = cell.find("m:v", NS)
                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
                elif value_node is None:
                    value = ""
                elif cell_type == "s":
                    value = shared_strings[int(value_node.text or "0")]
                else:
                    value = value_node.text or ""
                values[column] = normalize_text(value)
            row_map[row_number] = values

        merge_elements = root.find("m:mergeCells", NS)
        merged_ranges = tuple(
            element.attrib["ref"] for element in (list(merge_elements) if merge_elements is not None else [])
        )
        for merged_range in merged_ranges:
            start, end = merged_range.split(":")
            start_col, start_row = split_reference(start)
            end_col, end_row = split_reference(end)
            source_value = row_map.get(start_row, {}).get(start_col, "")
            if not source_value:
                continue
            for row_number in range(start_row, end_row + 1):
                row_values = row_map.setdefault(row_number, {"_row": str(row_number)})
                for number in range(column_number(start_col), column_number(end_col) + 1):
                    column = column_name(number)
                    if not row_values.get(column):
                        row_values[column] = source_value

        rows = tuple(row_map[number] for number in sorted(row_map))
        return Sheet(name=name, rows=rows, merged_ranges=merged_ranges)


def _stable_id(sheet: str, row: int, category: str, field: str = "") -> str:
    digest = hashlib.sha256(f"{sheet}|{row}|{category}|{field}".encode()).hexdigest()[:16]
    return f"kb-{digest}"


def _risk_classification(title: str, content: str) -> tuple[str, list[str]]:
    combined = f"{title}\n{content}"
    if (
        PHONE_RE.search(combined)
        or ID_RE.search(combined)
        or LONG_NUMBER_RE.search(combined)
        or ADDRESS_RE.search(combined)
        or any(term in title for term in ("退货地址", "收件人", "收货人"))
    ):
        return "excluded", ["sensitive_data"]

    handoff_tags = [tag for tag, words in HANDOFF_RULES.items() if any(word in combined for word in words)]
    if handoff_tags:
        return "handoff_only", handoff_tags

    review_tags = [tag for tag, words in REVIEW_RULES.items() if any(word in combined for word in words)]
    if review_tags:
        return "review_required", review_tags
    return "active", []


def _document(
    *,
    source_file: str,
    sheet: str,
    row: int,
    category: str,
    title: str,
    content: str,
    tags: list[str],
    field: str = "",
    force_status: str | None = None,
    extra_risk_tags: list[str] | None = None,
) -> dict[str, Any] | None:
    title = normalize_text(title)
    content = normalize_text(content)
    if not title or not content:
        return None
    status, risk_tags = _risk_classification(title, content)
    if force_status:
        status = force_status
    risk_tags = sorted(set(risk_tags + (extra_risk_tags or [])))
    if status == "excluded":
        return None
    return {
        "id": _stable_id(sheet, row, category, field),
        "title": title,
        "content": content,
        "tags": sorted({normalize_text(tag) for tag in tags if normalize_text(tag)}),
        "category": category,
        "status": status,
        "risk_tags": risk_tags,
        "source": {"file": source_file, "sheet": sheet, "row": row, "field": field},
    }


def _split_statements(value: str) -> list[str]:
    lines = [normalize_text(line) for line in value.split("\n") if normalize_text(line)]
    return lines or ([normalize_text(value)] if normalize_text(value) else [])


def _report_preview(value: str, limit: int = 180) -> str:
    """Keep build reports useful without copying private fulfilment data into Git."""
    normalized = normalize_text(value)
    if (
        PHONE_RE.search(normalized)
        or ID_RE.search(normalized)
        or LONG_NUMBER_RE.search(normalized)
        or ADDRESS_RE.search(normalized)
        or any(term in normalized for term in ("退货地址", "仓库退货组", "收件人", "收货人"))
    ):
        return "[敏感履约信息已排除]"
    return normalized[:limit]


def _product_documents(sheet: Sheet, source_file: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for row in sheet.rows[1:]:
        row_number = int(row["_row"])
        product_name = row.get("A", "")
        nickname = row.get("B", "")
        selling_points = row.get("C", "")
        usage = row.get("D", "")
        contraindications = row.get("E", "")
        notes = row.get("F", "")
        if product_name == "/":
            product_name = ""

        # The canonical workbook overloads D/E for hair-care pairing plans and
        # vertically merges A as a category label. Normalize that mini-table
        # before applying the regular skin-care column semantics.
        is_hair_product = product_name == "护发产品" and nickname in HAIR_PRODUCT_NAMES
        if is_hair_product:
            display_name = HAIR_PRODUCT_NAMES[nickname]
            base_tags = [display_name, nickname, "护发产品", "产品"]
            if selling_points:
                doc = _document(
                    source_file=source_file,
                    sheet=sheet.name,
                    row=row_number,
                    category="product_overview",
                    title=f"{display_name}（{nickname}）产品介绍",
                    content=selling_points,
                    tags=base_tags + ["成分", "卖点", "适用人群", "功效"],
                    field="selling_points",
                )
                if doc:
                    documents.append(doc)
            for pairing_index, pairing in enumerate(
                (value for value in (usage, contraindications) if value), 1
            ):
                doc = _document(
                    source_file=source_file,
                    sheet=sheet.name,
                    row=row_number,
                    category="product_note",
                    title=f"{display_name}（{nickname}）搭配与使用建议",
                    content=pairing,
                    tags=base_tags + ["搭配", "使用建议", "洗护组合"],
                    field=f"pairing_{pairing_index}",
                )
                if doc:
                    documents.append(doc)
            continue

        comparison_name = nickname or product_name
        is_comparison = bool("区别" in comparison_name and selling_points)
        if is_comparison:
            doc = _document(
                source_file=source_file,
                sheet=sheet.name,
                row=row_number,
                category="product_comparison",
                title=comparison_name,
                content=selling_points,
                tags=[comparison_name, "产品区别", "产品选择"],
            )
            if doc:
                documents.append(doc)
            continue

        display_name = product_name or nickname
        if not display_name:
            continue
        base_tags = [display_name, nickname, "产品"]
        if selling_points:
            doc = _document(
                source_file=source_file,
                sheet=sheet.name,
                row=row_number,
                category="product_overview",
                title=f"{display_name}（{nickname}）产品介绍" if nickname and nickname not in display_name else f"{display_name}产品介绍",
                content=selling_points,
                tags=base_tags + ["成分", "卖点", "适合肤质", "功效"],
                field="selling_points",
            )
            if doc:
                documents.append(doc)
        if usage:
            doc = _document(
                source_file=source_file,
                sheet=sheet.name,
                row=row_number,
                category="product_usage",
                title=f"{display_name}怎么使用",
                content=usage,
                tags=base_tags + ["使用方法", "用量", "使用顺序", "早晚"],
                field="usage",
            )
            if doc:
                documents.append(doc)
        for index, statement in enumerate(_split_statements(contraindications), 1):
            doc = _document(
                source_file=source_file,
                sheet=sheet.name,
                row=row_number,
                category="product_contraindication",
                title=f"{display_name}使用禁忌",
                content=statement,
                tags=base_tags + ["使用禁忌", "不能搭配", "孕妇"],
                field=f"contraindication_{index}",
            )
            if doc:
                documents.append(doc)
        if notes:
            doc = _document(
                source_file=source_file,
                sheet=sheet.name,
                row=row_number,
                category="product_note",
                title=f"{display_name}补充说明",
                content=notes,
                tags=base_tags + ["补充说明", "搭配"],
                field="notes",
            )
            if doc:
                documents.append(doc)
    return documents


def _faq_documents(sheet: Sheet, source_file: str) -> tuple[list[dict[str, Any]], int]:
    question_column, answer_columns = FAQ_SHEETS[sheet.name]
    documents: list[dict[str, Any]] = []
    skipped = 0
    for row in sheet.rows[1:]:
        row_number = int(row["_row"])
        question = row.get(question_column, "")
        answers = []
        for column in answer_columns:
            answer = row.get(column, "")
            if answer and answer not in answers:
                answers.append(answer)
        if not question or not answers:
            skipped += 1
            continue
        if "常用话术" in question:
            skipped += 1
            continue
        content = "\n\n".join(
            f"标准话术 {index}：{answer}" if len(answers) > 1 else answer
            for index, answer in enumerate(answers, 1)
        )
        status, risk_tags = _risk_classification(question, content)
        if status == "excluded":
            skipped += 1
            continue
        doc = _document(
            source_file=source_file,
            sheet=sheet.name,
            row=row_number,
            category="customer_service_faq",
            title=question,
            content=content,
            tags=[question, "客服话术", sheet.name],
            force_status=status,
            extra_risk_tags=risk_tags,
        )
        if doc:
            documents.append(doc)
    return documents, skipped


def _product_field_map(sheet: Sheet) -> dict[str, dict[str, tuple[str, int]]]:
    result: dict[str, dict[str, tuple[str, int]]] = defaultdict(dict)
    for row in sheet.rows[1:]:
        row_number = int(row["_row"])
        name = row.get("B", "") or row.get("A", "")
        key = normalize_key(name)
        if not key:
            continue
        for column, field in (("C", "selling_points"), ("D", "usage"), ("E", "contraindications")):
            value = normalize_text(row.get(column, ""))
            if value and value != "/":
                result[key][field] = (value, row_number)
    return result


def _product_core(value: str) -> str:
    key = normalize_key(value)
    for suffix in ("精华液", "精华乳", "精华油", "精华", "面霜", "乳霜", "洗发水"):
        key = key.replace(suffix, "")
    return key


def _apply_numeric_fact_conflicts(
    canonical_sheet: Sheet, documents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    products: dict[str, dict[str, Any]] = {}
    for row in canonical_sheet.rows[1:]:
        nickname = row.get("B", "")
        product_name = row.get("A", "")
        core = _product_core(nickname or product_name)
        if len(core) < 3:
            continue
        source_text = "\n".join(row.get(column, "") for column in ("A", "B", "C", "D", "E", "F"))
        percentages = set(PERCENT_RE.findall(source_text))
        if percentages:
            products[core] = {
                "name": nickname or product_name,
                "percentages": percentages,
                "row": int(row["_row"]),
            }

    conflicts: list[dict[str, Any]] = []
    for document in documents:
        if document["category"] != "customer_service_faq":
            continue
        document_text = normalize_key(document["title"] + "\n" + document["content"])
        document_percentages = set(PERCENT_RE.findall(document["title"] + "\n" + document["content"]))
        if not document_percentages:
            continue
        for core, product in products.items():
            if core not in document_text:
                continue
            unexpected = document_percentages - product["percentages"]
            if not unexpected or not product["percentages"].isdisjoint(document_percentages):
                continue
            if document["status"] == "active":
                document["status"] = "review_required"
            document["risk_tags"] = sorted(set(document["risk_tags"] + ["canonical_numeric_conflict"]))
            conflicts.append(
                {
                    "type": "canonical_numeric_conflict",
                    "product": product["name"],
                    "canonical_source": f"{CANONICAL_PRODUCT_SHEET}!{product['row']}",
                    "other_source": f"{document['source']['sheet']}!{document['source']['row']}",
                    "canonical_percentages": sorted(product["percentages"]),
                    "other_percentages": sorted(document_percentages),
                    "unexpected_percentages": sorted(unexpected),
                }
            )
    return conflicts


def _conflicts(sheets: dict[str, Sheet], documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts = _apply_numeric_fact_conflicts(sheets[CANONICAL_PRODUCT_SHEET], documents)
    canonical = _product_field_map(sheets[CANONICAL_PRODUCT_SHEET])
    legacy = _product_field_map(sheets[LEGACY_PRODUCT_SHEET])
    for product in sorted(canonical.keys() & legacy.keys()):
        for field in sorted(canonical[product].keys() & legacy[product].keys()):
            current, current_row = canonical[product][field]
            old, old_row = legacy[product][field]
            if normalize_key(current) != normalize_key(old):
                conflicts.append(
                    {
                        "type": "product_version_conflict",
                        "product_key": product,
                        "field": field,
                        "canonical_source": f"{CANONICAL_PRODUCT_SHEET}!{current_row}",
                        "legacy_source": f"{LEGACY_PRODUCT_SHEET}!{old_row}",
                        "canonical_preview": _report_preview(current),
                        "legacy_preview": _report_preview(old),
                    }
                )

    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        if document["category"] == "customer_service_faq":
            by_title[normalize_key(document["title"])].append(document)
    for title_key, group in sorted(by_title.items()):
        unique_answers = {normalize_key(document["content"]) for document in group}
        if title_key and len(group) > 1 and len(unique_answers) > 1:
            conflicts.append(
                {
                    "type": "faq_answer_conflict",
                    "title_key": title_key,
                    "sources": [
                        f"{document['source']['sheet']}!{document['source']['row']}" for document in group
                    ],
                    "previews": [_report_preview(document["content"]) for document in group],
                }
            )
    return conflicts


def _deduplicate_documents(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    status_rank = {"active": 0, "review_required": 1, "handoff_only": 2}
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    merged = 0
    for document in documents:
        key = (
            normalize_key(document["title"]),
            normalize_key(document["content"]),
            document["category"],
        )
        existing = unique.get(key)
        if existing is None:
            document["alternate_sources"] = []
            unique[key] = document
            continue
        merged += 1
        existing["alternate_sources"].append(document["source"])
        existing["tags"] = sorted(set(existing["tags"] + document["tags"]))
        existing["risk_tags"] = sorted(set(existing["risk_tags"] + document["risk_tags"]))
        if status_rank[document["status"]] > status_rank[existing["status"]]:
            existing["status"] = document["status"]
    return list(unique.values()), merged


def build_knowledge(source_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_path = source_path.resolve()
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    sheets_list, image_count = XlsxWorkbook(source_path).read()
    sheets = {sheet.name: sheet for sheet in sheets_list}
    documents: list[dict[str, Any]] = []
    sheet_report: list[dict[str, Any]] = []

    for sheet in sheets_list:
        report_item: dict[str, Any] = {
            "sheet": sheet.name,
            "rows": max(0, len(sheet.rows) - 1),
            "header": sorted(sheet.header),
        }
        if ORDER_HEADERS.issubset(sheet.header):
            report_item.update({"decision": "excluded", "reason": "order_data_with_personal_or_transaction_data"})
        elif not sheet.rows:
            report_item.update({"decision": "excluded", "reason": "empty_sheet"})
        elif sheet.name == LEGACY_PRODUCT_SHEET:
            report_item.update({"decision": "review_only", "reason": "legacy_product_sheet_used_for_conflict_detection"})
        elif sheet.name == CANONICAL_PRODUCT_SHEET:
            added = _product_documents(sheet, source_path.name)
            documents.extend(added)
            report_item.update({"decision": "ingested", "documents": len(added)})
        elif sheet.name in FAQ_SHEETS:
            added, skipped = _faq_documents(sheet, source_path.name)
            documents.extend(added)
            report_item.update({"decision": "ingested", "documents": len(added), "skipped_rows": skipped})
        else:
            report_item.update({"decision": "excluded", "reason": "unsupported_or_unclassified_sheet"})
        sheet_report.append(report_item)

    raw_document_count = len(documents)
    conflicts = _conflicts(sheets, documents)
    documents, duplicates_merged = _deduplicate_documents(documents)
    documents.sort(key=lambda item: (item["source"]["sheet"], item["source"]["row"], item["id"]))
    status_counts = Counter(document["status"] for document in documents)
    category_counts = Counter(document["category"] for document in documents)
    risk_counts = Counter(tag for document in documents for tag in document["risk_tags"])

    knowledge = {
        "schema_version": "1.0",
        "source": {"file": source_path.name, "sha256": source_hash},
        "documents": documents,
    }
    report = {
        "schema_version": "1.0",
        "source": {"file": source_path.name, "sha256": source_hash},
        "summary": {
            "sheets": len(sheets_list),
            "embedded_images_reviewed": image_count,
            "documents": len(documents),
            "raw_documents": raw_document_count,
            "duplicates_merged": duplicates_merged,
            "active_documents": status_counts.get("active", 0),
            "review_required_documents": status_counts.get("review_required", 0),
            "handoff_only_documents": status_counts.get("handoff_only", 0),
            "conflicts": len(conflicts),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "risk_tag_counts": dict(sorted(risk_counts.items())),
        "sheets": sheet_report,
        "conflicts": conflicts,
        "decisions": [
            "Order sheets are excluded in full.",
            "The 三蛋丸 sheet is canonical; 三蛋丸产品介绍 is treated as legacy and only compared for conflicts.",
            "Rows containing phone, ID, or long transaction numbers are excluded.",
            "Adverse reaction and complex after-sales entries are handoff-only and not searchable for automatic answers.",
            "Pregnancy, medical, minor-use, absolute reassurance, and regulated-claim entries require human review.",
            "Embedded images were visually audited but are not OCR-ingested because their content is not authoritative structured text.",
        ],
    }
    return knowledge, report


def write_build_outputs(
    source_path: Path, knowledge_path: Path, report_path: Path
) -> tuple[int, dict[str, Any]]:
    knowledge, report = build_knowledge(source_path)
    knowledge_path.write_text(json.dumps(knowledge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(knowledge["documents"]), report
