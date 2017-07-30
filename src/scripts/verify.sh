#!/bin/sh
# Please run from the top level directory like src/scripts/verify.sh

PEP8_CMD="pep8 "
PYLINT_CMD="pylint -E "

 export PYTHONPATH=.

# Run pep8 on all python files.
echo "Checking pep8"
find src/ -name *.py -exec ${PEP8_CMD} '{}' \;

echo "Checking pylint"
# Run pylint on all python files.
find src/ -name *.py -exec ${PYLINT_CMD} '{}' \;
