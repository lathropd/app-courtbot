#!/usr/bin/env python3
"""Scrape Iowa Courts filings and email the recent-filing report."""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import os
from pathlib import Path
import random
import re
import smtplib
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from http.cookiejar import CookieJar
from typing import Iterable
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "filings.sqlite"
SPREADSHEET_URL = (
    "https://gannett-my.sharepoint.com/:x:/p/lgrundme/"
    "EZSlomu-naNFh5RcH6kQrQQBgJHGJ5laxSc6LfTAVNVuoQ?download=1"
)
COURT_LOGIN_URL = "https://www.iowacourts.state.ia.us/ESAWebApp/ESALogin.jsp"
USER_AGENT = (
    "Python courtbot. Email dlathrop@registermedia.com with questions "
    "or call (319) 244-8873"
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filings (
  case_number TEXT,
  case_title TEXT,
  event TEXT,
  filed_by TEXT,
  filed TEXT,
  create_date TEXT,
  last_updated TEXT,
  notes TEXT,
  status TEXT,
  unique(case_number, event, filed_by, filed, create_date, last_updated, notes)
);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO filings
  (case_number, case_title, event, filed_by, filed, create_date,
   last_updated, notes, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

NEW_FILINGS_SQL = """
select case_number, case_title, event, notes, filed, last_updated, filed_by
from filings
where event not in (
  'APPEARANCE',
  'RETURN OF SERVICE',
  'RETURN OF ORIGINAL NOTICE',
  'ACCEPTANCE OF SERVICE',
  'NOTICE OF DISCOVERY RESPONSE',
  'RETURN OF SERVICE ON SUBPOENA'
)
and (
  julianday(substr(last_updated, 7, 4) || "-" ||
            substr(last_updated, 1, 2) || "-" ||
            substr(last_updated, 4, 2)) > julianday("now") - 7
)
and status like 'new';
"""

UPDATE_STATUS_SQL = "update filings set status = strftime('%Y-%m-%d', 'now');"

COUNTY_CODES = {
    "ADAIR": "05011",
    "ADAMS": "05021",
    "ALLAMAKEE": "01031",
    "APPANOOSE": "08041",
    "AUDUBON": "04051",
    "BENTON": "06061",
    "BLACK HAWK": "01071",
    "BOONE": "02081",
    "BREMER": "02091",
    "BUCHANAN": "01101",
    "BUENA VISTA": "03111",
    "BUTLER": "02121",
    "CALHOUN": "02131",
    "CARROLL": "02141",
    "CASS": "04151",
    "CEDAR": "07161",
    "CERRO GORDO": "02171",
    "CHEROKEE": "03181",
    "CHICKASAW": "01191",
    "CLARKE": "05201",
    "CLAY": "03211",
    "CLAYTON": "01221",
    "CLINTON": "07231",
    "CRAWFORD": "03241",
    "DALLAS": "05251",
    "DAVIS": "08261",
    "DECATUR": "05271",
    "DELAWARE": "01281",
    "DES MOINES": "08291",
    "DICKINSON": "03301",
    "DUBUQUE": "01311",
    "EMMET": "03321",
    "FAYETTE": "01331",
    "FLOYD": "02341",
    "FRANKLIN": "02351",
    "FREMONT": "04361",
    "GREENE": "02371",
    "GRUNDY": "01381",
    "GUTHRIE": "05391",
    "HAMILTON": "02401",
    "HANCOCK": "02411",
    "HARDIN": "02421",
    "HARRISON": "04431",
    "HENRY": "08441",
    "HOWARD": "01451",
    "HUMBOLDT": "02461",
    "IDA": "03471",
    "IOWA": "06481",
    "JACKSON": "07491",
    "JASPER": "05501",
    "JEFFERSON": "08511",
    "JOHNSON": "06521",
    "JONES": "06531",
    "KEOKUK": "08541",
    "KOSSUTH": "03551",
    "LEE (SOUTH)": "08561",
    "LEE (NORTH)": "08562",
    "LEE": "08561",
    "LINN": "06571",
    "LOUISA": "08581",
    "LUCAS": "05591",
    "LYON": "03601",
    "MADISON": "05611",
    "MAHASKA": "08621",
    "MARION": "05631",
    "MARSHALL": "02641",
    "MILLS": "04651",
    "MITCHELL": "02661",
    "MONONA": "03671",
    "MONROE": "08681",
    "MONTGOMERY": "04691",
    "MUSCATINE": "07701",
    "OBRIEN": "03711",
    "OSCEOLA": "03721",
    "PAGE": "04731",
    "PALO ALTO": "03741",
    "PLYMOUTH": "03751",
    "POCAHONTAS": "02761",
    "POLK": "05771",
    "POTTAWATTAMIE": "04781",
    "POWESHIEK": "08791",
    "RINGGOLD": "05801",
    "SAC": "02811",
    "SCOTT": "07821",
    "SHELBY": "04831",
    "SIOUX": "03841",
    "STORY": "02851",
    "TAMA": "06861",
    "TAYLOR": "05871",
    "UNION": "05881",
    "VAN BUREN": "08891",
    "WAPELLO": "08901",
    "WARREN": "05911",
    "WASHINGTON": "08921",
    "WAYNE": "05931",
    "WEBSTER": "02941",
    "WINNEBAGO": "02951",
    "WINNESHIEK": "01961",
    "WOODBURY": "03971",
    "WORTH": "02981",
    "WRIGHT": "02991",
}


@dataclass
class Link:
    attrs: dict[str, str]
    text: str = ""


@dataclass
class Form:
    attrs: dict[str, str]
    fields: dict[str, str] = field(default_factory=dict)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self.forms: list[Form] = []
        self.tables: list[list[list[str]]] = []
        self._link: Link | None = None
        self._form: Form | None = None
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "a":
            self._link = Link(attr)
        elif tag == "form":
            self._form = Form(attr)
        elif tag == "input" and self._form is not None:
            name = attr.get("name")
            if name:
                self._form.fields[name] = attr.get("value", "")
        elif tag == "select" and self._form is not None:
            name = attr.get("name")
            if name and name not in self._form.fields:
                self._form.fields[name] = ""
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._link is not None:
            self._link.text += data
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link is not None:
            self._link.text = clean_text(self._link.text)
            self.links.append(self._link)
            self._link = None
        elif tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(clean_text(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


class Browser:
    def __init__(self) -> None:
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.url = ""
        self.content = ""
        self.parser = PageParser()

    def get(self, url: str) -> str:
        return self.open(urljoin(self.url, url))

    def open(self, url: str, data: bytes | None = None) -> str:
        request = Request(url, data=data, headers={"User-Agent": USER_AGENT})
        with self.opener.open(request, timeout=60) as response:
            raw = response.read()
            self.url = response.geturl()
            charset = response.headers.get_content_charset() or "ISO-8859-1"
            self.content = raw.decode(charset, errors="replace")
        self.parser = PageParser()
        self.parser.feed(self.content)
        return self.content

    def follow_link(
        self,
        *,
        text: str | None = None,
        name: str | None = None,
        url: str | None = None,
    ) -> str:
        for link in self.parser.links:
            href = link.attrs.get("href", "")
            if text is not None and link.text != text:
                continue
            if name is not None and link.attrs.get("name") != name:
                continue
            if url is not None:
                expected = urljoin(self.url, url)
                actual = urljoin(self.url, href)
                if href != url and actual != expected:
                    continue
            if not href:
                raise RuntimeError(f"Matched link has no href: {link}")
            return self.get(href)
        raise RuntimeError(f"Link not found: text={text!r} name={name!r} url={url!r}")

    def submit_form(
        self,
        *,
        number: int | None = None,
        name: str | None = None,
        fields: dict[str, str],
    ) -> str:
        form = self._find_form(number=number, name=name)
        values = dict(form.fields)
        values.update(fields)
        action = form.attrs.get("action") or self.url
        method = form.attrs.get("method", "get").lower()
        target = urljoin(self.url, action)
        encoded = urlencode(values).encode()
        if method == "post":
            return self.open(target, encoded)
        separator = "&" if "?" in target else "?"
        return self.get(f"{target}{separator}{encoded.decode()}")

    def _find_form(self, *, number: int | None, name: str | None) -> Form:
        if number is not None:
            index = number - 1
            if 0 <= index < len(self.parser.forms):
                return self.parser.forms[index]
        if name is not None:
            for form in self.parser.forms:
                if form.attrs.get("name") == name:
                    return form
        raise RuntimeError(f"Form not found: number={number!r} name={name!r}")


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def init_db(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    return conn


def download_file(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with build_opener().open(request, timeout=60) as response:
        path.write_bytes(response.read())


def xlsx_sheet_rows(path: Path, sheet_name: str) -> list[list[str]]:
    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive, ns)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = None
        for candidate in workbook.findall("main:sheets/main:sheet", ns):
            if candidate.attrib.get("name") == sheet_name:
                sheet = candidate
                break
        if sheet is None:
            raise RuntimeError(f"Worksheet not found: {sheet_name}")

        rel_id = sheet.attrib[f"{{{ns['rel']}}}id"]
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rels.findall("pkgrel:Relationship", ns):
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib["Target"].lstrip("/")
                break
        if target is None:
            raise RuntimeError(f"Worksheet relationship not found: {rel_id}")
        sheet_path = f"xl/{target}" if not target.startswith("xl/") else target
        worksheet = ET.fromstring(archive.read(sheet_path))

    rows: list[list[str]] = []
    for row_el in worksheet.findall("main:sheetData/main:row", ns):
        row_values: dict[int, str] = {}
        for cell in row_el.findall("main:c", ns):
            ref = cell.attrib.get("r", "")
            column = column_index(ref)
            value_el = cell.find("main:v", ns)
            inline_el = cell.find("main:is/main:t", ns)
            if inline_el is not None:
                value = inline_el.text or ""
            elif value_el is None:
                value = ""
            elif cell.attrib.get("t") == "s":
                value = shared_strings[int(value_el.text or "0")]
            else:
                value = value_el.text or ""
            row_values[column] = clean_text(value)
        width = max(row_values.keys(), default=-1) + 1
        rows.append([row_values.get(i, "") for i in range(width)])
    return rows


def read_shared_strings(archive: zipfile.ZipFile, ns: dict[str, str]) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    strings = []
    for item in root.findall("main:si", ns):
        parts = [text.text or "" for text in item.findall(".//main:t", ns)]
        strings.append("".join(parts))
    return strings


def column_index(cell_reference: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_reference)
    if not letters:
        return 0
    index = 0
    for char in letters.group(1):
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


def cases_from_spreadsheet(path: Path) -> list[str]:
    cases = []
    for row in xlsx_sheet_rows(path, "Active Cases")[1:]:
        next_date = row[2] if len(row) > 2 else ""
        case_num = row[6] if len(row) > 6 else ""
        if not next_date or not case_num:
            continue
        match = re.search(r"([A-Z]{4,6}.\d+\s+\([A-Za-z ]+\))", case_num)
        if match:
            cases.append(match.group(1).upper())
    return cases


def normalize_case(case: str) -> str | None:
    match = re.match(r"(.+)\s+\((.+)\)", case)
    if not match:
        return None
    case_id, county = match.groups()
    county_code = COUNTY_CODES.get(county)
    if not county_code:
        print(f"Skipping case with unknown county {county!r}: {case}", file=sys.stderr)
        return None
    return f"{county_code} {case_id}"


def parse_filing_rows(content: str, caseid: str) -> tuple[str, list[list[str]]]:
    parser = PageParser()
    parser.feed(content)
    if not parser.tables:
        raise RuntimeError(f"No filings table found for {caseid}")
    rows = parser.tables[0]
    if len(rows) < 2:
        raise RuntimeError(f"Filings table is missing rows for {caseid}")

    case_info = rows[0][0] if rows and rows[0] else ""
    title_match = re.search(r"Title:\s*(.*)", case_info)
    case_title = clean_text(title_match.group(1) if title_match else "")
    data_rows = rows[2:]

    records: list[list[str]] = []
    record: list[str] = []
    for row in data_rows:
        cells = [clean_text(cell) for cell in row]
        while len(cells) < 7:
            cells.append("")
        if cells[1]:
            if record:
                record[6] = clean_text(record[6])
                records.append(record)
            cells[6] = ""
            record = cells
        elif record and record[6]:
            record[6] = clean_text(f"{record[6]} {cells[0]}")
        elif record:
            record[6] = cells[0]
    if record:
        record[6] = clean_text(record[6])
        records.append(record)

    return case_title, [record for record in records if record and record[0]]


def scrape(args: argparse.Namespace) -> None:
    conn = init_db(args.db)
    tmp_xlsx = BASE_DIR / "tmp.xlsx"
    print(f"{datetime.now():%F %T}", file=sys.stderr)
    print("Downloading active case spreadsheet", file=sys.stderr)
    download_file(SPREADSHEET_URL, tmp_xlsx)

    raw_cases = cases_from_spreadsheet(tmp_xlsx)
    cases = [case for case in (normalize_case(item) for item in raw_cases) if case]
    print(f"Opened spreadsheet with {len(raw_cases)} cases.", file=sys.stderr)

    browser = Browser()
    browser.open(COURT_LOGIN_URL)
    print("submit login", file=sys.stderr)
    browser.submit_form(
        number=1,
        fields={
            "userid": require_env("COURTBOT_USER"),
            "password": require_env("COURTBOT_PASSWORD"),
        },
    )
    if "Login Error" in browser.content:
        raise RuntimeError("Iowa Courts login failed")

    print("login success", file=sys.stderr)
    time.sleep(random.random() * 2)
    try:
        for case in cases:
            scrape_case(browser, conn, case, args.sleep)
    finally:
        conn.commit()
        conn.close()
        logout(browser)
        print(f"{datetime.now():%F %T}", file=sys.stderr)


def scrape_case(browser: Browser, conn: sqlite3.Connection, case: str, sleep: bool) -> None:
    print(case)
    if sleep:
        time.sleep(1 + random.random() * 5)
    browser.get("https://www.iowacourts.state.ia.us/")
    browser.get("https://www.iowacourts.state.ia.us/ESAWebApp/DefaultFrame")
    browser.follow_link(text="Click Here to Search")
    browser.follow_link(name="main")
    browser.follow_link(url="/ESAWebApp/TrialSimpFrame")
    browser.follow_link(name="main")
    if sleep:
        time.sleep(random.random() * 3)

    match = re.match(r"(\d{5})(.*)(\w\w)(\w\w\d{6})", case)
    if not match:
        print(f"Could not parse case id: {case}", file=sys.stderr)
        return
    county, city, case_type, number = match.groups()
    print(f"case: {case}", file=sys.stderr)
    browser.submit_form(
        name="TrailCourtStateWide",
        fields={
            "caseid1": county,
            "caseid2": clean_text(city),
            "caseid3": case_type,
            "caseid4": number,
            "searchtype": "C",
        },
    )
    case_match = re.search(r"mySubmit\('(\d{5})(..)(..)(..\d{6}),'(.*)'\)", browser.content)
    if not case_match:
        print(f"No search result matched for {case}", file=sys.stderr)
        return
    caseid = "".join(case_match.groups()[:4])

    browser.submit_form(name="TrialForm", fields={"caseid": caseid})
    browser.follow_link(name="banner")
    browser.follow_link(text="Filings")
    case_title, rows = parse_filing_rows(browser.content, caseid)
    for event in rows:
        conn.execute(
            INSERT_SQL,
            (
                caseid,
                case_title,
                event[0],
                event[1],
                event[2],
                event[3],
                event[4],
                event[6],
                "new",
            ),
        )
    conn.commit()


def logout(browser: Browser) -> None:
    print("log out", file=sys.stderr)
    try:
        browser.get("https://www.iowacourts.state.ia.us/ESAWebApp/TrialCourtStateWide")
        browser.submit_form(name="logoffForm", fields={})
        print("logged out", file=sys.stderr)
    except Exception as exc:
        print(f"Log out failed: {exc}", file=sys.stderr)


def render_rows_as_html(rows: Iterable[sqlite3.Row]) -> str:
    output = [read_header_html()]
    first = True
    columns: list[str] = []
    for row in rows:
        if first:
            columns = row.keys()
            output.append("<TR>" + "".join(f"<TH>{html.escape(col)}</TH>" for col in columns) + "</TR>")
            first = False
        output.append(
            "<TR>"
            + "".join(f"<TD>{html.escape(str(row[col] or ''))}</TD>" for col in columns)
            + "</TR>"
        )
    output.append("</table>")
    return "\n".join(output)


def read_header_html() -> str:
    return (BASE_DIR / "header.html").read_text()


def email_report(args: argparse.Namespace) -> None:
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rows = list(conn.execute(NEW_FILINGS_SQL))
        table = render_rows_as_html(rows)
        conn.execute(UPDATE_STATUS_SQL)
        conn.commit()
    finally:
        conn.close()

    msg = EmailMessage()
    msg["Subject"] = "Court bot results"
    msg["From"] = require_env("GMAIL_USER")
    msg["To"] = ", ".join(args.recipients)
    msg.set_content("Recent filings are available in the HTML version of this message.")
    msg.add_alternative(
        f"""<html><head></head>
<body>
<p>Recent filings</p>
{table}
<p><small>Brought to you by Daniel Lathrop and the letter p.</small></p>
</body>
</html>""",
        subtype="html",
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(require_env("GMAIL_USER"), require_env("GMAIL_PWD"))
        smtp.send_message(msg)


def run_all(args: argparse.Namespace) -> None:
    scrape(args)
    email_report(args)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--sleep", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--recipient",
        action="append",
        dest="recipients",
        default=[
            "wrmorris2@registermedia.com",
            "metroia@registermedia.com",
            "pjoens@registermedia.com",
            "dlathrop@registermedia.com",
            "nelhajj@registermedia.com",
            "kwerner@gannett.com",
            "ccrowder@registermedia.com",
        ],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scrape")
    subparsers.add_parser("email")
    subparsers.add_parser("run")
    args = parser.parse_args(argv)
    if args.command == "scrape":
        args.func = scrape
    elif args.command == "email":
        args.func = email_report
    else:
        args.func = run_all
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
