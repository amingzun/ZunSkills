# ZunSkills

陈明军的 AI 技能池，用来沉淀可复用的 Codex skills。这里的 skill 以长期复用为目标，尽量把工作流、脚本、配置模板和运行约束放在一起，避免散落在临时项目目录里。

## Skills

- `resume-pdf-maker`：明尊简历PDF生成器。用于从简历内容或已有文件生成可确认、可预览、可导出的简历 PDF。
- `ai-daily-radar`：每日 AI 资讯雷达。每天从国外 AI 社区、论文、开源项目、官方发布、技术资讯和 GitHub 快速增长 AI 工具库中收集最多 100 条候选，按推荐分和来源多样性输出 Top 50 阅读型 Markdown 日报，并额外生成面向未来 WebUI 的 `items.json`。日报以“AI 资讯主编”视角输出主编一句话、这条在说什么、主编怎么看、读者行动和术语解释；支持可选 QQ 邮箱 SMTP 发送。

## Structure

```text
skills/
  resume-pdf-maker/
    SKILL.md
    agents/
    scripts/
    tests/
  ai-daily-radar/
    SKILL.md
    agents/
    scripts/
    templates/
```

## Usage

把需要使用的 skill 复制或安装到本机 Codex skills 目录，例如：

```bash
cp -R skills/resume-pdf-maker ~/.codex/skills/resume-pdf-maker
```

安装 AI Daily Radar：

```bash
cp -R skills/ai-daily-radar ~/.codex/skills/ai-daily-radar
```

运行 AI Daily Radar：

```bash
python3 ~/.codex/skills/ai-daily-radar/scripts/ai_daily_radar.py \
  --config ~/.codex/skills/ai-daily-radar/templates/config.example.json
```

输出文件默认位于 `~/.codex/skills/ai-daily-radar/outputs/`：

- `YYYY-MM-DD-ai-daily-radar.md`：适合直接阅读的中文 AI 资讯日报，按主编点评卡片组织。
- `YYYY-MM-DD-items.json`：面向后续资讯流 WebUI 的结构化数据，包含 `editor_note`、`what_happened`、`why_it_matters`、`reader_takeaway` 和 `summary_status`。
- `YYYY-MM-DD-source-health.json`：后台排查用的来源健康信息，不作为读者主界面内容。

如需邮件发送，在本机创建私有配置文件 `~/.codex/ai-daily-radar-email.env`，不要把授权码提交到仓库：

```bash
AI_DAILY_RADAR_SEND_EMAIL=1
AI_DAILY_RADAR_QQ_USER=your-qq-number@qq.com
AI_DAILY_RADAR_QQ_AUTH_CODE=your-qq-mail-smtp-authorization-code
AI_DAILY_RADAR_EMAIL_TO=recipient@qq.com
```
