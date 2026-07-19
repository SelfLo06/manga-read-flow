"""Reusable experiment packages grouped by numbered stage directories.

The physical directories follow the documentation numbering scheme.  Import-safe
aliases keep normal Python imports available without duplicating the code.
"""

from importlib import import_module
import sys


_STAGE_ALIASES = {
    "grouping_120": "120-grouping",
    "ocr_130": "130-ocr",
    "translation_140": "140-translation",
    "cleaning_150": "150-cleaning",
    "typesetting_160": "160-typesetting",
}

for _alias, _physical_name in _STAGE_ALIASES.items():
    _module = import_module(f"{__name__}.{_physical_name}")
    sys.modules[f"{__name__}.{_alias}"] = _module
    globals()[_alias] = _module

__all__ = list(_STAGE_ALIASES)
