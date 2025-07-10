rm -rf build dist *.egg-info

python -m build

twine check --strict dist/*
pip install -U packaging
twine check --strict dist/*

twine upload dist/*
# Note Authenticate: 
# When prompted, enter __token__ for the username and your PyPI API token for the password.