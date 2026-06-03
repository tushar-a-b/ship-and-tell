"""Entry point for `ship-and-tell-ui` -- shells out to `streamlit run` on ui.py."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        sys.stderr.write(
            "streamlit is not installed. Reinstall with the UI extras:\n"
            "    pip install -e '.[ui]'\n"
        )
        sys.exit(1)

    ui_path = Path(__file__).parent / "ui.py"
    sys.argv = ["streamlit", "run", str(ui_path), *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
