import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import resume_pdf_maker


class ResumePdfMakerTest(unittest.TestCase):
    def test_module_imports(self):
        self.assertTrue(hasattr(resume_pdf_maker, "main"))

    def test_safe_name_keeps_chinese_and_removes_path_chars(self):
        self.assertEqual(resume_pdf_maker.safe_name("郑敏慧"), "郑敏慧")
        self.assertEqual(resume_pdf_maker.safe_name("张/三:客服"), "张三客服")
        self.assertEqual(resume_pdf_maker.safe_name("   "), "未命名")

    def test_file_names_for_resume(self):
        names = resume_pdf_maker.file_names("郑敏慧")
        self.assertEqual(names["markdown"], "简历_郑敏慧.md")
        self.assertEqual(names["pdf"], "简历_郑敏慧.pdf")
        self.assertEqual(names["stable_html"], "resume_郑敏慧_保守稳重.html")
        self.assertNotIn("stable_png", names)

    def test_markdown_resume_contains_sections(self):
        data = {
            "name": "郑敏慧",
            "phone": "18267072195",
            "email": "1849356186@qq.com",
            "location": "浙江省磐安县",
            "summary": "认真负责，沟通高效。",
            "education": [
                {
                    "school": "浙江广播电视大学",
                    "major": "行政管理",
                    "degree": "大专",
                    "date": "2024年1月毕业",
                }
            ],
            "experience": [
                {
                    "company": "浙江瑞文医药",
                    "role": "电商客服",
                    "date": "2022年4月1日－2026年3月31日",
                    "bullets": ["完成客户录入及订单管理"],
                }
            ],
            "skills": ["熟练使用 Word、Excel、PPT"],
            "certificates": ["母婴护理员证"],
        }
        md = resume_pdf_maker.render_markdown(data)
        self.assertIn("# 郑敏慧", md)
        self.assertIn("## 工作经历", md)
        self.assertIn("- 完成客户录入及订单管理", md)

    def test_validate_html_document_accepts_resume_structure(self):
        html = """<!doctype html>
<html lang="zh-CN">
<head><style>@page { size: A4; margin: 0; }</style></head>
<body><main class="page"><div class="portrait"></div></main></body>
</html>"""
        resume_pdf_maker.validate_html_document(html)

    def test_validate_html_document_rejects_missing_structure(self):
        with self.assertRaises(ValueError):
            resume_pdf_maker.validate_html_document("<html><body>plain</body></html>")

    def test_write_html_validates_and_writes(self):
        html = """<!doctype html>
<html lang="zh-CN">
<head><style>@page { size: A4; margin: 0; }</style></head>
<body><main class="page"><div class="portrait"></div></main></body>
</html>"""
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "resume.html"
            resume_pdf_maker.write_html(out, html)
            self.assertEqual(out.read_text(encoding="utf-8"), html)

    def test_photo_data_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = pathlib.Path(tmp) / "photo.jpg"
            photo.write_bytes(b"abc")
            uri = resume_pdf_maker.photo_data_uri(photo)
        self.assertEqual(uri, "data:image/jpeg;base64,YWJj")

    def test_ensure_workdir_uses_safe_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = resume_pdf_maker.ensure_workdir(pathlib.Path(tmp), "张/三:客服")
            self.assertEqual(workdir.name, "张三客服")
            self.assertTrue(workdir.is_dir())

    def test_run_chrome_uses_isolated_profile_and_crash_suppression(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = pathlib.Path(tmp) / "chrome"
            chrome.write_text("", encoding="utf-8")
            proc = mock.Mock()
            proc.poll.return_value = 0
            with mock.patch.object(resume_pdf_maker, "CHROME", chrome), mock.patch(
                "resume_pdf_maker.subprocess.Popen", return_value=proc
            ) as popen:
                resume_pdf_maker.run_chrome(["--print-to-pdf=/tmp/out.pdf", "file:///tmp/in.html"])
        command = popen.call_args.args[0]
        self.assertIn("--headless=new", command)
        self.assertIn("--disable-crash-reporter", command)
        self.assertIn("--disable-breakpad", command)
        self.assertIn("--disable-session-crashed-bubble", command)
        self.assertIn("--noerrdialogs", command)
        self.assertIn("--no-first-run", command)
        self.assertTrue(any(arg.startswith("--user-data-dir=") for arg in command))
        self.assertIn("--print-to-pdf=/tmp/out.pdf", command)
        self.assertEqual(popen.call_args.kwargs["stdout"], resume_pdf_maker.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["stderr"], resume_pdf_maker.subprocess.DEVNULL)

    def test_expected_output_path_detects_pdf_target(self):
        path = resume_pdf_maker.expected_output_path(["--print-to-pdf=/tmp/out.pdf", "file:///tmp/in.html"])
        self.assertEqual(path, pathlib.Path("/tmp/out.pdf"))

    def test_run_chrome_does_not_force_quit_after_pdf_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = pathlib.Path(tmp) / "chrome"
            chrome.write_text("", encoding="utf-8")
            out = pathlib.Path(tmp) / "out.pdf"
            out.write_bytes(b"%PDF-1.4")
            proc = mock.Mock()
            proc.poll.return_value = None
            proc.wait.side_effect = [
                resume_pdf_maker.subprocess.TimeoutExpired(cmd=["chrome"], timeout=1),
                0,
            ]
            with mock.patch.object(resume_pdf_maker, "CHROME", chrome), mock.patch(
                "resume_pdf_maker.subprocess.Popen", return_value=proc
            ), mock.patch.object(resume_pdf_maker, "CHROME_GRACE_SECONDS", 0.01):
                resume_pdf_maker.run_chrome([f"--print-to-pdf={out}", "file:///tmp/in.html"])
            self.assertFalse(proc.terminate.called)
            self.assertFalse(proc.kill.called)


if __name__ == "__main__":
    unittest.main()
