import json
from pathlib import Path

from story_state import rebuild_story_state_from_locked


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    result = rebuild_story_state_from_locked(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
