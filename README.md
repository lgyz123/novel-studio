# novel-studio

## 项目简介
单 Agent 本地小说写作系统原型，采用文件工作流，便于后续扩展。

## 目录说明
- `00_manifest/`：小说总纲、世界观、人物卡等设定模板
- `01_inputs/`：写作任务、生活素材、参考资料
- `02_working/`：大纲、草稿、修订稿、日志等工作区
- `03_locked/`：已锁定的章节与正典内容
- `prompts/`：Agent 提示词与输出 schema
- `app/`：主程序、配置与依赖

## 第一阶段目标
- 实现最小可运行的单 Agent 写作原型
- 仅支持本地文件流转，不引入数据库和多 agent

## 如何运行
### 本地运行
1. 创建虚拟环境：`python3 -m venv app/.venv`
2. 激活虚拟环境：
	 - macOS / Linux：`source app/.venv/bin/activate`
	 - Windows PowerShell：`./app/.venv/Scripts/Activate.ps1`
3. 安装依赖：`pip install -r app/requirements.txt`
4. 运行主程序：`python app/main.py`

### Codespaces
- 仓库已提供 `.devcontainer/` 配置
- 首次创建 Codespace 时会自动：
	- 创建 `app/.venv`
	- 安装 `app/requirements.txt`
	- 为终端自动激活 `app/.venv`
- Codespaces 运行在 Linux 容器中，因此默认使用 `source app/.venv/bin/activate` 这一套环境逻辑

## Git 使用建议
- 建议每次大改前先 commit
- `02_working/logs/` 下日志文件已自动忽略
- 不要将敏感信息提交到仓库
