from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python3 app/set_current_task.py <task_file_path>")
        sys.exit(1)

    src = ROOT / sys.argv[1]
    dst = ROOT / "01_inputs/tasks/current_task.md"

    if not src.exists():
        print(f"找不到任务文件: {src}")
        sys.exit(1)

    shutil.copyfile(src, dst)
    print(f"已设置当前任务: {src} -> {dst}")


if __name__ == "__main__":
    main()