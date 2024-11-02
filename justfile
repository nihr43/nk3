apply: lint
  nix-shell . --run 'python3 main.py'

upgrade: lint
  nix-shell . --run 'python3 main.py -u'

test: lint
  nix-shell . --run 'python3 tests/test_main.py'
  nix-shell . --run 'python3 main.py -i artifacts/test_inventory.yaml --skip-initial'

lint:
  black .
  flake8 . --ignore=E501,W503
