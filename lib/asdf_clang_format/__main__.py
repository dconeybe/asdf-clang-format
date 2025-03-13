import sys

from .plugin import main

try:
  main()
except KeyboardInterrupt:
  print("ERROR: application terminated by keyboard interrupt", file=sys.stderr)
  sys.exit(1)
