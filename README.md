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
1. 安装依赖：`pip install -r app/requirements.txt`
2. 运行主程序：`python app/main.py`

## Git 使用建议
- 建议每次大改前先 commit
- `02_working/logs/` 下日志文件已自动忽略
- 不要将敏感信息提交到仓库
