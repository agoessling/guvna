# GuVNA contributor instructions

Manually hard-wrap lines to at most 100 characters in repository text files, including prose, code,
comments, and configuration. Break prose at word boundaries and split code at syntax-safe points.
An editor ruler at column 100 helps during editing.

Before handing off changes, run this from the repository root. It reports file names and line
numbers for lines longer than 100 characters. An empty result (exit code 1) means the check passed.

```sh
rg --hidden --no-heading -n -g '!.git' '.{101}' .
```
