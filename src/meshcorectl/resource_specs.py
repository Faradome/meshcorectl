"""Registers every resource kind's table layout with `output.resources`.

Importing this module (once, from `cli.py`) is what makes
`output.render(rows, fmt, kind="contact")` etc. work -- see
`output/resources.py` for the registry itself. Keeping every registration
in one file makes the full set of resource kinds/columns easy to scan in
one place instead of scattered across each command module.
"""

from __future__ import annotations

from .output.resources import ResourceSpec, register

register(
    "device",
    ResourceSpec(
        columns=(("NAME", "name"), ("MODEL", "model"), ("VERSION", "ver")),
        wide_columns=(
            ("FW-PROTOCOL", "fw ver"),
            ("BUILD", "fw_build"),
            ("PUBLIC-KEY", "public_key"),
        ),
    ),
)

register(
    "contact",
    ResourceSpec(
        columns=(("NAME", "name"), ("TYPE", "type"), ("PATH", "path")),
        wide_columns=(
            ("PUBLIC-KEY", "public_key"),
            ("LAST-ADVERT", "last_advert"),
            ("FLAGS", "flags"),
        ),
    ),
)

register(
    "channel",
    ResourceSpec(
        columns=(("INDEX", "index"), ("NAME", "name")),
        wide_columns=(("SECRET", "secret"),),
    ),
)

register(
    "pending-contact",
    ResourceSpec(
        columns=(("NAME", "name"), ("TYPE", "type"), ("PUBLIC-KEY", "public_key")),
    ),
)

register(
    "time",
    ResourceSpec(columns=(("EPOCH", "epoch"), ("TIME", "time"))),
)

register(
    "path",
    ResourceSpec(columns=(("NAME", "name"), ("PATH", "path"))),
)

register(
    "telemetry",
    ResourceSpec(columns=(("CHANNEL", "channel"), ("TYPE", "type"), ("VALUE", "value"))),
)

register(
    "telemetry-history",
    ResourceSpec(
        columns=(
            ("CHANNEL", "channel"),
            ("TYPE", "type"),
            ("MIN", "min"),
            ("MAX", "max"),
            ("AVG", "avg"),
        )
    ),
)

register(
    "scan-result",
    ResourceSpec(columns=(("KIND", "kind"), ("ADDRESS", "address"), ("NAME", "name"))),
)
