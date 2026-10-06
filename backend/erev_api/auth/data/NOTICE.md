# Third-party data: `common-passwords.txt`

`common-passwords.txt` is the bundled common-password list of the password policy (03 REQ-PLT-004; 05 SAR-06; `erev_api/auth/passwords.py`). It replaces the generator output recorded by SPEC-Q-128 (PLF review PR-C-06; D-86a). Tests read this file and this notice only, with no network.

## Source

| Field | Value |
|---|---|
| Project | SecLists, https://github.com/danielmiessler/SecLists |
| Commit | `8f4c1846cdb02a7024bd09decce1afc1ef5df46b` (`refs/heads/master` from `git ls-remote`, 2026-09-16) |
| Source file | `Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt` |
| Download URL | https://raw.githubusercontent.com/danielmiessler/SecLists/8f4c1846cdb02a7024bd09decce1afc1ef5df46b/Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt |
| Source file size | 8,557,632 bytes; 1,000,000 lines, most frequent first |
| SHA-256 of the source file | `424a3e03a17df0a2bc2b3ca749d81b04e79d59cb7aeec8876a5a3f308d0caf51` |
| Licence | MIT (the SecLists `LICENSE` at the commit above, reproduced below) |
| SHA-256 of the SecLists `LICENSE` | `3dbdc93d5f8829de0941744841730a09c106d0732e5ae0e98ca1d77be7ded66c` |
| Downloaded | 2026-09-16, once, by lane L7-4 (D-86a). The source file is not vendored |

The source file is the frequency-ranked top 1,000,000 of the xato.net "10 million passwords" corpus as SecLists publishes it. The licence recorded here is the SecLists repository licence. Terms at the level of the corpus were not checked.

## Derivation

The policy refuses a password shorter than 12 characters before it consults the list, and it compares `password.lower()` with the entries. So the vendored list keeps the 10,000 most frequent distinct lowercase entries of 12 or more characters, in source order:

```python
from pathlib import Path

source = Path("xato-net-10-million-passwords-1000000.txt")
entries: list[str] = []
seen: set[str] = set()
for raw in source.read_text(encoding="utf-8").splitlines():
    entry = raw.lower()
    if len(entry) < 12 or entry in seen:
        continue
    seen.add(entry)
    entries.append(entry)
    if len(entries) == 10_000:
        break
Path("common-passwords.txt").write_bytes(("\n".join(entries) + "\n").encode("utf-8"))
```

- The 10,000th entry comes from source line 611,665. The first entries are `123qweasdzxc`, `1qaz2wsx3edc`, `q1w2e3r4t5y6`, `1q2w3e4r5t6y`.
- Output: 10,000 lines, 140,276 bytes, printable ASCII, LF line endings.
- SHA-256 of `common-passwords.txt`: `ec8c0a3e04cb76025fbb33469bd8e5b35def58cc913649e548237ffed657a4eb`
- Ranks in the vendored list: `1q2w3e4r5t6y` 4, `111111111111` 67, `123123123123` 78, `password1234` 96, `qwertyuiop12` 268.

The D-86a example, SecLists `Passwords/Common-Credentials/10k-most-common.txt` at the same commit (SHA-256 `68782d6a4a19a4768d5f15dd66bd534e7a33055cc755411e33f16d18c50fdcce`, 10,001 lines), was downloaded and not used. Only 10 of its entries have 12 or more characters. It holds neither `password1234`, which the BUILD_SPEC acceptance tests refuse, nor the PR-C-06 examples `111111111111`, `123123123123` and `1q2w3e4r5t6y`.

## Licence text

```
MIT License

Copyright (c) 2018 Daniel Miessler

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
