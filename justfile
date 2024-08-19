apply: lint
  nix-shell . --run 'python3 main.py'

upgrade: lint
  nix-shell . --run 'python3 main.py -u'

test: lint
  nix-shell . --run 'python3 tests/test.py'

lint:
  black .
  flake8 . --ignore=E501,W503
