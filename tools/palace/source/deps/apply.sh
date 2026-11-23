#!/bin/sh
# ExternalProject supplies a private source tree. Snapshot it so repeated patch steps always start
# from the exact same archive contents, including when several dependent patches touch one file.
set -eu
if ! git --git-dir=.git rev-parse --verify --quiet HEAD >/dev/null; then
    git init -q
    git add -f .
    export GIT_AUTHOR_DATE=2000-01-01T00:00:00Z GIT_COMMITTER_DATE=2000-01-01T00:00:00Z
    git -c user.name=GuVNA -c user.email=build@localhost commit -qm pristine
fi
git reset --hard --quiet
git clean -fdq
git apply "$@"
