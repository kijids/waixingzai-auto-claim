# -*- coding: utf-8 -*-
"""不连手机的单元测试：进度解析、锁定判断、按钮定位。

CI 里不需要安卓设备，也不需要 GUI。
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import ad_runner  # noqa: E402
import ocr_reader  # noqa: E402


def dump(rows):
    """rows: [(text, y)] → uiautomator 风格的 XML。"""
    nodes = "".join(
        f'<node text="{t}" bounds="[100,{y}][400,{y + 40}]" />' for t, y in rows)
    return ('<hierarchy rotation="0"><node bounds="[0,0][1260,2800]">'
            + nodes + "</node></hierarchy>")


def ocr_rows(rows):
    out = []
    for text, y in rows:
        out.append({
            "text": text, "norm": text.replace(" ", ""),
            "x1": 100, "y1": y, "x2": 400, "y2": y + 40,
            "cx": 250, "cy": y + 20,
        })
    return out


PARTIAL = [
    ("阶段一", 1080), ("7/9", 1086),
    ("阶段二", 1480), ("待解锁", 1486),
    ("加油包", 1804), ("待解锁", 1770),
    ("点广告 领时长", 2100),
]

DONE = [
    ("阶段一", 1080), ("已完成", 1086),
    ("阶段二", 1480), ("已完成", 1486),
    ("加油包", 1804), ("已完成", 1770),
]


class TestProgress(unittest.TestCase):
    def test_partial_with_locked(self):
        prog = ad_runner.parse_progress(dump(PARTIAL))
        self.assertEqual(prog["阶段一"]["cur"], 7)
        self.assertEqual(prog["阶段一"]["total"], 9)
        self.assertFalse(prog["阶段一"]["done"])
        self.assertTrue(prog["阶段二"]["locked"])
        self.assertTrue(prog["加油包"]["locked"])
        # 顺序解锁：这一轮只该跑阶段一剩下的 2 条
        self.assertEqual(ad_runner.remaining_now(prog, ad_runner.DEFAULT_TARGETS), 2)

    def test_all_done(self):
        prog = ad_runner.parse_progress(dump(DONE))
        self.assertTrue(all(prog[n]["done"] for n in ad_runner.PHASE_NAMES))
        self.assertEqual(ad_runner.remaining_now(prog, ad_runner.DEFAULT_TARGETS), 0)

    def test_line_text(self):
        prog = ad_runner.parse_progress(dump(PARTIAL))
        line, remain = ad_runner.progress_line(prog, ad_runner.DEFAULT_TARGETS)
        self.assertIn("阶段一 7/9", line)
        self.assertIn("待解锁", line)
        self.assertEqual(remain, 2)

    def test_ocr_progress_matches(self):
        prog = ocr_reader.progress(ocr_rows(PARTIAL))
        self.assertEqual(prog["阶段一"]["cur"], 7)
        self.assertTrue(prog["阶段二"]["locked"])
        self.assertEqual(ad_runner.remaining_now(prog, ad_runner.DEFAULT_TARGETS), 2)


class TestCta(unittest.TestCase):
    def test_skip_title_line(self):
        rows = ocr_rows([("点广告 免费玩", 520), ("点广告 领时长", 2100)])
        hit = ocr_reader.find_cta(rows)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["cy"], 2120)   # 按钮那一行，不是标题

    def test_none_when_finished(self):
        rows = ocr_rows([("点广告 免费玩", 520), ("今日已领完", 900)])
        self.assertIsNone(ocr_reader.find_cta(rows))

    def test_merged_split_button(self):
        rows = ocr_rows([("点广土亽", 2100), ("口领时长", 2100)])
        for r in rows:
            r["x1"] = 460 if "领时长" in r["norm"] else 520
            r["x2"] = 780
        hit = ocr_reader.find_cta(rows)
        self.assertIsNotNone(hit)


if __name__ == "__main__":
    unittest.main()
