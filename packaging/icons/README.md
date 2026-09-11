# Icons

The build looks for two files here and carries on without them:

| File | Used by |
|---|---|
| `earcongen.ico` | the Windows executable |
| `earcongen.icns` | the macOS app bundle |

Neither is committed. A build with no icons is correct — it just gets the
platform's default — so a fork can produce working binaries without
supplying artwork.

Six candidate marks are in `candidates/`, with notes on what each one
says and where each is weak, plus the commands for turning the winner
into the two files above.

Linux binaries take no icon at build time; a desktop entry supplies one.

If you add them, 256×256 is enough for the `.ico`; an `.icns` wants the
full set from 16 up to 1024, which `iconutil -c icns` will assemble from
an `.iconset` directory on macOS.
