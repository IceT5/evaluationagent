# Package entry point
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from evaluator.cli.app import run_cli

if __name__ == "__main__":
    run_cli()
