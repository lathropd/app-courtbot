import sqlite3
import tempfile
import unittest
from pathlib import Path

import courtbot


class CourtbotTests(unittest.TestCase):
    def test_parse_filing_rows_combines_multiline_notes(self):
        content = """
        <table>
          <tr><td>Case Number: 05771 FECR335644
          Title: STATE VS EXAMPLE</td></tr>
          <tr><th>Event</th><th>Filed By</th><th>Filed</th><th>Create</th>
          <th>Last Updated</th><th>Other</th><th>Notes</th></tr>
          <tr><td>MOTION</td><td>SMITH JANE</td><td>01/19/2022</td>
          <td>01/19/2022</td><td>01/20/2022</td><td></td><td></td></tr>
          <tr><td>Comments: FIRST LINE</td><td></td><td></td><td></td>
          <td></td><td></td><td></td></tr>
          <tr><td>SECOND LINE</td><td></td><td></td><td></td>
          <td></td><td></td><td></td></tr>
        </table>
        """

        title, rows = courtbot.parse_filing_rows(content, "05771FECR335644")

        self.assertEqual(title, "STATE VS EXAMPLE")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "MOTION")
        self.assertEqual(rows[0][6], "Comments: FIRST LINE SECOND LINE")

    def test_render_rows_as_html_escapes_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "filings.sqlite"
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            conn.execute("create table rows (name text)")
            conn.execute("insert into rows values (?)", ("A&B",))
            rows = list(conn.execute("select name from rows"))

        rendered = courtbot.render_rows_as_html(rows)

        self.assertIn("<TH>name</TH>", rendered)
        self.assertIn("<TD>A&amp;B</TD>", rendered)


if __name__ == "__main__":
    unittest.main()
