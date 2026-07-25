from __future__ import annotations

from datetime import date, timedelta
import os
import time
from typing import Iterable
import xml.etree.ElementTree as ET

from ..models import ResearchItem
from ..normalize import classify, clean_text, normalize_doi
from .base import get_json, session

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _text(node: ET.Element | None) -> str:
    return "".join(node.itertext()).strip() if node is not None else ""


def _pub_date(article: ET.Element) -> str:
    for path in (
        ".//ArticleDate",
        ".//JournalIssue/PubDate",
        ".//PubMedPubDate[@PubStatus='pubmed']",
        ".//PubMedPubDate",
    ):
        node = article.find(path)
        if node is None:
            continue
        year = _text(node.find("Year"))
        month = _text(node.find("Month")) or "01"
        day = _text(node.find("Day")) or "01"
        months = {name: f"{index:02d}" for index, name in enumerate(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
        )}
        month = months.get(month[:3].title(), month.zfill(2) if month.isdigit() else "01")
        if year:
            return f"{year}-{month}-{day.zfill(2)}"
    return ""


class PubMedSource:
    def __init__(self, topic_config: dict, api_key: str = ""):
        self.topics = topic_config
        self.api_key = api_key or os.getenv("NCBI_API_KEY", "")
        self.http = session()

    def _params(self, values: dict) -> dict:
        values = {**values, "tool": "research-radar", "email": "zrxzrx1227@163.com"}
        if self.api_key:
            values["api_key"] = self.api_key
        return values

    def search(
        self,
        days: int,
        journal_aliases: Iterable[str] | None = None,
        retmax: int = 500,
        extra_term: str = "",
    ) -> tuple[list[str], dict]:
        start = date.today() - timedelta(days=days)
        date_term = f'("{start:%Y/%m/%d}"[Date - Publication] : "{date.today():%Y/%m/%d}"[Date - Publication])'
        if journal_aliases:
            journal_term = " OR ".join(f'"{name}"[Journal]' for name in journal_aliases)
            query = f"{date_term} AND ({journal_term})"
        else:
            query = f"{date_term} AND medline[sb]"
        if extra_term.strip():
            query = f"{query} AND {extra_term.strip()}"
        params = self._params(
            {"db": "pubmed", "term": query, "retmode": "json", "retmax": min(retmax, 10000), "sort": "pub date"}
        )
        payload = get_json(f"{EUTILS}/esearch.fcgi", params)
        return payload.get("esearchresult", {}).get("idlist", []), payload

    def fetch(self, pmids: list[str], kind: str = "paper") -> tuple[list[ResearchItem], list[str]]:
        items: list[ResearchItem] = []
        raw_batches: list[str] = []
        for offset in range(0, len(pmids), 200):
            batch = pmids[offset : offset + 200]
            response = self.http.get(
                f"{EUTILS}/efetch.fcgi",
                params=self._params({"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}),
                timeout=90,
            )
            response.raise_for_status()
            raw_batches.append(response.text)
            root = ET.fromstring(response.content)
            for record in root.findall(".//PubmedArticle"):
                citation = record.find("MedlineCitation")
                article = record.find(".//Article")
                if citation is None or article is None:
                    continue
                pmid = _text(citation.find("PMID"))
                title = _text(article.find("ArticleTitle"))
                abstract = " ".join(_text(node) for node in article.findall(".//AbstractText"))
                journal = _text(article.find(".//Journal/Title"))
                issns = [_text(node) for node in article.findall(".//ISSN")]
                issns.extend(_text(node) for node in record.findall(".//ISSNLinking"))
                doi = ""
                for identifier in record.findall(".//ArticleId"):
                    if identifier.attrib.get("IdType") == "doi":
                        doi = _text(identifier)
                        break
                mesh = [_text(node) for node in record.findall(".//MeshHeading/DescriptorName")]
                publication_types = [_text(node).casefold() for node in article.findall(".//PublicationType")]
                retracted = any("retract" in value for value in publication_types)
                categories = classify(f"{title} {abstract} {' '.join(mesh)}", self.topics)
                item = ResearchItem(
                    kind=kind,
                    source_id="pubmed",
                    source_name="PubMed",
                    title=title,
                    summary=abstract,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                    doi=doi,
                    pmid=pmid,
                    journal=journal,
                    issns=issns,
                    published_at=_pub_date(record),
                    language=_text(article.find("Language")),
                    categories=categories,
                    mesh_terms=mesh,
                    is_retracted=retracted,
                    provenance={"database": "PubMed", "publication_types": publication_types},
                ).finalize()
                if item.title:
                    items.append(item)
            if offset + 200 < len(pmids):
                time.sleep(0.35 if self.api_key else 0.7)
        return items, raw_batches

    def collect(
        self,
        days: int,
        journal_aliases: Iterable[str] | None = None,
        retmax: int = 500,
        extra_term: str = "",
    ) -> tuple[list[ResearchItem], dict]:
        pmids, search_payload = self.search(days, journal_aliases, retmax, extra_term)
        items, xml_batches = self.fetch(pmids)
        return items, {"search": search_payload, "fetch_xml": xml_batches}


class EuropePMCEnricher:
    endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def enrich(self, items: list[ResearchItem], max_items: int = 100) -> dict:
        raw: dict[str, dict] = {}
        candidates = [item for item in items if item.pmid and (not item.summary or not item.doi)]
        for item in candidates[:max_items]:
            if not item.pmid:
                continue
            payload = get_json(
                self.endpoint,
                {"query": f"EXT_ID:{item.pmid} AND SRC:MED", "format": "json", "resultType": "core", "pageSize": 1},
            )
            raw[item.pmid] = payload
            results = payload.get("resultList", {}).get("result", [])
            if not results:
                continue
            result = results[0]
            if not item.summary:
                item.summary = clean_text(result.get("abstractText", ""))
            if not item.doi:
                item.doi = normalize_doi(result.get("doi", ""))
            item.provenance["europe_pmc_cited_by_count"] = result.get("citedByCount", 0)
        return raw


class OpenAlexEnricher:
    endpoint = "https://api.openalex.org/works"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("OPENALEX_API_KEY", "")

    def enrich(self, items: list[ResearchItem], max_items: int = 500) -> dict:
        if not self.api_key:
            return {}
        raw: dict[str, dict] = {}
        eligible = [item for item in items[:max_items] if item.doi]
        by_doi = {item.doi: item for item in eligible}
        for offset in range(0, len(eligible), 25):
            batch = eligible[offset : offset + 25]
            payload = get_json(
                self.endpoint,
                {
                    "api_key": self.api_key,
                    "filter": "doi:" + "|".join(f"https://doi.org/{item.doi}" for item in batch),
                    "per_page": 25,
                    "select": "id,doi,primary_topic,citation_normalized_percentile,is_retracted",
                },
            )
            raw[f"batch-{offset // 25 + 1}"] = payload
            for result in payload.get("results", []):
                doi = normalize_doi(result.get("doi", ""))
                item = by_doi.get(doi)
                if not item:
                    continue
                topic = result.get("primary_topic") or {}
                item.primary_topic = topic.get("display_name", "") or item.primary_topic
                percentile = result.get("citation_normalized_percentile") or {}
                item.citation_percentile = float(percentile.get("value") or 0.0)
                item.is_retracted = item.is_retracted or bool(result.get("is_retracted"))
                item.provenance["openalex_id"] = result.get("id", "")
            time.sleep(0.1)
        return raw
