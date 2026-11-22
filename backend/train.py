"""Train the takeover-learning policy and save it as model.json.

  python train.py                    train on 30 scripted-operator demonstrations (default)
  python train.py --scripted 50      ... on 50 of them
  python train.py --from-db          train on your own takeovers from takeovers.db
"""
import argparse
from pathlib import Path

import db
import scripted_operator
from learning import KNNPolicy

parser = argparse.ArgumentParser()
parser.add_argument("--from-db", action="store_true", help="use real takeovers from takeovers.db")
parser.add_argument("--scripted", type=int, default=30, help="number of scripted demonstrations")
parser.add_argument("--seed", type=int, default=123)
parser.add_argument("--out", default=str(Path(__file__).parent / "model.json"))
args = parser.parse_args()

if args.from_db:
    episodes = db.load_episodes(outcomes=("success", "handed_back"))
    source = "real takeovers"
else:
    episodes = scripted_operator.make_demos(args.scripted, seed=args.seed)
    source = "scripted operator"

if not episodes:
    raise SystemExit("No episodes to train on.")

policy = KNNPolicy().fit(episodes, source=source)
policy.save(args.out)
print(f"Trained on {policy.meta['demos']} demonstrations ({policy.meta['samples']} decisions, "
      f"source: {source}) -> {args.out}")
