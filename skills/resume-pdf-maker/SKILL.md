---
name: resume-pdf-maker
description: |
  Use when the user wants to create, polish, redesign, convert, or export a resume PDF from rough content or an existing file; compare three AI-generated HTML resume designs; approve an HTML preview; embed a photo; and produce final 简历_姓名.pdf. Chinese display name: 明尊简历PDF生成器.
---

# 明尊简历PDF生成器 resume-pdf-maker

Use this skill to turn resume material or an existing resume file into a user-approved PDF. Keep the workflow gated: confirm the written resume first, confirm the selected HTML preview second, then export.

## Non-Negotiable Gates

Never export the final PDF until both gates are complete:

1. Markdown content confirmation: the user explicitly confirms the resume text is accurate and complete.
2. HTML preview approval: the user explicitly approves the selected HTML file for PDF export.

Do not treat an existing resume file, rough content, or a style preference as approval for either gate.

## Entry Paths

- Start from content: organize the user's rough resume text into structured resume data.
- Start from file: extract content from `.docx`, `.pdf`, `.html`, `.md`, `.txt`, or OCR text when available, then use the same confirmation flow.

Do not invent achievements, numbers, dates, certificates, employers, schools, or contact details. Improve wording only from facts the user supplied or confirmed.

## Forbidden Content Changes

Do not:

- Invent or upgrade education, certificates, employers, roles, dates, awards, tools, systems, salary, or management scope.
- Add metrics such as percentages, order volume, sales, customer satisfaction, cost savings, or efficiency gains unless the user supplied or confirmed them.
- Turn ordinary duties into exaggerated claims such as "led", "managed", "owned", "optimized end-to-end", or "built systems" when the facts only support participation or routine execution.
- Change contact information, location, graduation time, birth date, or photo identity without explicit user confirmation.
- Hide uncertainty. If a resume fact is unclear, mark it as needing confirmation in the Markdown preview instead of guessing.

## Working Folder And Names

Create one flat working folder in the current working directory named after the confirmed resume name, such as `郑敏慧/`. If the name is unknown, use `resume-draft-YYYYMMDD-HHMM/` temporarily, then move or continue in the confirmed name folder.

Put generated assets directly inside that one folder. Do not create nested folders by default.

Use these names:

- Markdown: `简历_姓名.md`
- HTML variants: `resume_姓名_保守稳重.html`, `resume_姓名_清爽专业.html`, `resume_姓名_高级设计感.html`
- Photo copy: `照片_姓名.jpg`
- Final PDF: `简历_姓名.pdf`

The final filename must be exactly `简历_姓名.pdf` with the confirmed name substituted.

## Content Confirmation

Normalize available content into resume sections: personal information, target role, education, work experience, project or internship experience, skills, certificates, self-evaluation, and photo requirements.

The target role is required before design work. If the user did not provide one, ask for the intended role, role family, or delivery context such as `电商客服`, `行政文员`, `护理岗`, `收银员`, `通用求职`, or `先做通用版`. Use the target role to tune wording, section order, density, and visual style, but do not invent facts to make the resume fit that role.

Check in this order:

1. Accuracy: name, phone, email, location, education, company names, roles, dates, certificates.
2. Completeness: target role, recent experience, key skills, graduation time, photo.
3. Consistency: reverse chronological order, date overlap or gaps, contact format.
4. Expression quality: concise resume wording and consistent style.

Before any design work:

1. Save the normalized resume as `简历_姓名.md` in the working folder.
2. Show the same Markdown in chat as a copyable preview. If no copy UI is available, use a clean fenced Markdown block.
3. Ask the user to confirm whether the content is accurate and complete.
4. Apply corrections and repeat the preview until the user confirms.

Offer deeper resume consulting only when useful or requested. Ask targeted questions about role, industry, outcomes, measurable impact, tools, and keywords, then return to the Markdown confirmation gate.

## AI HTML Design And Preview Approval

After Markdown content confirmation, dynamically generate three complete HTML files with AI. Do not use a fixed dead template for the final designs. Use the confirmed Markdown as the only source of resume facts.

- `Markdown-Resume 经典紧凑风`: inspired by the CyC2018 Markdown-Resume direction without copying its source. Use a document-like black-and-white resume, compact spacing, clear heading rules, small icon or label accents only when useful, and strong one-page density.
- `Typora Markdown 简洁技术风`: inspired by the CodingDocs Typora Markdown resume direction without copying its source. Use a clean Markdown/technical-resume feel, readable tables or aligned metadata rows when useful, crisp skill/project sections, and moderate whitespace.
- `蓝色侧栏服务岗视觉风`: inspired by the user-provided blue sidebar reference image. Use a blue left sidebar for photo, name, basic information, skills, and certificates; use a white right content area for education, work experience, and self-evaluation; use blue section titles, simple icon circles, and timeline nodes where they improve scanning.

Support custom style instructions such as `医院护理岗亲和一点`, `黑白极简`, `国企正式`, `互联网简洁`, or `跟参考图一致`. A custom direction may replace one default variant or guide all three.

Do not download, copy, or embed source files from the referenced GitHub templates unless the user explicitly asks for source reuse and license review. Treat them as visual/structural inspiration only.

To control token cost, use a compact generation frame for each HTML instead of lengthy design prose:

- Generate one self-contained HTML file per style.
- Keep CSS in the HTML.
- Include `@page`, `.page`, and `.portrait`.
- Prefer one page; adapt density to content length with font size, line height, spacing, section grouping, and column choices.
- Use confirmed Markdown content only; never add unconfirmed employers, dates, schools, certificates, metrics, or claims.
- Make the three designs meaningfully different in structure, rhythm, typography, and accent treatment, not just color.
- Keep the photo area stable and compatible with later photo embedding.
- Avoid decorative clutter that hurts resume readability.
- For long content, compress intelligently: reduce vertical rhythm, use two-column skill/certificate blocks, combine short metadata into inline rows, and keep job bullets concise. For short content, increase whitespace and hierarchy rather than stretching text.

The minimum structural contract for each HTML is:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    @page { size: 1086px 1450px; margin: 0; }
    .page { width: 1086px; min-height: 1450px; }
    .portrait { overflow: hidden; }
    .portrait img { width: 100%; height: 100%; object-fit: cover; object-position: center top; display: block; }
  </style>
</head>
<body><main class="page">...</main></body>
</html>
```

Save AI-generated HTML through `write-html` so the helper validates the core structure. Provide the three HTML file links to the user and ask them to open/preview them. Ask the user to choose one style. Allow one focused revision by default, such as photo crop, font size, spacing, accent color, title style, wording, or minor layout. Continue revisions only if the user explicitly asks to keep editing.

Never export the PDF before the selected HTML file is approved.

## Photo Handling

When the user provides a photo, copy it into the working folder as `照片_姓名.jpg` and embed it in the selected HTML. Use this default photo CSS:

```css
object-fit: cover;
object-position: center top;
```

If no photo is available, keep a placeholder in drafts if helpful. Before final export, ask whether the user wants to proceed without a photo.

## Script Usage

Prefer the local helper for deterministic file operations:

```bash
python3 scripts/resume_pdf_maker.py write-md --base "$PWD" --data resume.json
python3 scripts/resume_pdf_maker.py write-html --out "姓名/resume_姓名_清爽专业.html" < generated.html
python3 scripts/resume_pdf_maker.py embed-photo --html "姓名/resume_姓名_清爽专业.html" --photo "姓名/照片_姓名.jpg" --out "姓名/resume_姓名_清爽专业_final.html"
python3 scripts/resume_pdf_maker.py pdf --html "姓名/resume_姓名_清爽专业_final.html" --out "姓名/简历_姓名.pdf"
python3 scripts/resume_pdf_maker.py verify --pdf "姓名/简历_姓名.pdf"
```

Use the script from the skill root, or adjust paths if running from another directory. The `pdf` command uses an isolated temporary Chrome profile and disables crash reporting/recovery flags so exports do not affect the user's normal Chrome profile.

## Final Verification

After export, verify:

- The PDF exists.
- The file starts with a valid `%PDF-` header.
- The page count is reasonable for a resume.
- The filename and path end in `简历_姓名.pdf`.
- The selected HTML contains the embedded photo when a photo was provided.

Report completed checks and provide the final PDF path. Mention any verification step that could not be performed.

## Final Artifact List

At completion, list the files produced in the working folder, using clickable paths when available:

- Markdown source: `简历_姓名.md`
- Selected or final HTML: chosen `resume_姓名_*.html` and any `_final.html` file
- Photo copy, when provided: `照片_姓名.jpg`
- Final PDF: `简历_姓名.pdf`
- PNG preview, when rendered for visual checking: `简历_姓名.png`

If an artifact was not produced because the user skipped that step, say so plainly.
