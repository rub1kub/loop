#!/usr/bin/env python3
"""Render public demo assets with the production LOOP result-card renderer."""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api"))

from app.result_cards import CardFacts, render_result_card  # noqa: E402


def main() -> None:
    output = REPOSITORY_ROOT / "docs" / "share-cards"
    output.mkdir(parents=True, exist_ok=True)
    samples = {
        "bank-result-demo.jpg": CardFacts(
            public_id="loop-bank-public-demo",
            mode="bank",
            payout_nano=3_000_000_000,
            contributed_nano=2_000_000_000,
            result_nano=1_000_000_000,
            demo=True,
        ),
        "duel-result-demo.jpg": CardFacts(
            public_id="loop-duel-public-demo",
            mode="duel",
            payout_nano=1_950_000_000,
            contributed_nano=1_000_000_000,
            result_nano=950_000_000,
            demo=True,
        ),
    }
    for name, facts in samples.items():
        path = output / name
        path.write_bytes(render_result_card(facts))
        print(path.relative_to(REPOSITORY_ROOT))


if __name__ == "__main__":
    main()
