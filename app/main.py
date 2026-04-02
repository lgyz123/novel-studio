import os
import sys
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')

REQUIRED_DIRS = [
    '../00_manifest',
    '../01_inputs',
    '../02_working',
    '../03_locked',
    '../prompts',
]

def check_dirs():
    missing = []
    for d in REQUIRED_DIRS:
        abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), d))
        if not os.path.isdir(abs_path):
            missing.append(abs_path)
    return missing

def main():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"配置文件读取失败: {e}")
        sys.exit(1)

    missing_dirs = check_dirs()
    if missing_dirs:
        print("缺少以下关键目录：")
        for d in missing_dirs:
            print(f"  - {d}")
        sys.exit(1)

    print("项目初始化完成。配置加载成功，关键目录均已存在。")

if __name__ == "__main__":
    main()
