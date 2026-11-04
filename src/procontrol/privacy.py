"""Pseudonymisation of natural persons.

Peruvian suppliers can be natural persons (RUC prefixes 10, 15 and 17 are issued to individuals;
the 8 digits after "10" are usually the person's DNI). Their name and document are personal
data, so they are replaced *at ingestion time* - before anything reaches the warehouse, the
outputs or the site - by a keyed hash:

    token = HMAC-SHA256(key, normalised_document)[:16]
    id    -> "NP-<token>"
    name  -> "Natural person NP-<token>"
    ruc   -> None

* Keyed (HMAC) rather than a plain hash: a plain SHA-256 of an 8-digit DNI can be reversed by
  brute force in seconds; without the key it cannot.
* Deterministic: the same person gets the same token in every run with the same key, so
  aggregation by supplier still works.
* The key is read from an environment variable (``PROCONTROL_SALT`` by default) and is never
  written to disk. With no key set a public demo key is used and a warning is printed - fine for
  synthetic data, not acceptable for real data.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import warnings
from dataclasses import dataclass

DEMO_KEY = "procontrol-public-demo-key-not-secret"

_DIGITS = re.compile(r"\D+")


@dataclass(frozen=True)
class Party:
    id: str
    name: str | None
    ruc: str | None
    is_natural_person: bool


class Pseudonymiser:
    def __init__(self, key: str | None = None, natural_prefixes: tuple[str, ...] = ("10", "15", "17"),
                 env_var: str = "PROCONTROL_SALT"):
        key = key or os.environ.get(env_var)
        if not key:
            warnings.warn(
                f"{env_var} is not set: using the public demo key. Set a secret key before "
                "processing real data.",
                stacklevel=2,
            )
            key = DEMO_KEY
        self._key = key.encode("utf-8")
        self.natural_prefixes = natural_prefixes
        self._cache: dict[tuple, Party] = {}

    def token(self, document: str) -> str:
        norm = _DIGITS.sub("", document) or document.strip().upper()
        return hmac.new(self._key, norm.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    def is_natural(self, scheme: str | None, doc: str | None) -> bool:
        if not doc:
            return False
        if scheme and "DNI" in scheme.upper():
            return True
        digits = _DIGITS.sub("", doc)
        return len(digits) == 11 and digits[:2] in self.natural_prefixes

    def party(self, party_id: str | None, name: str | None, scheme: str | None,
              doc: str | None) -> Party:
        """Return the party, pseudonymised if it is a natural person."""
        if doc is None and party_id:
            # Fall back to an identifier embedded in the party id (e.g. "PE-RUC-10xxxxxxxxx").
            m = re.search(r"(\d{8,11})$", party_id)
            doc = m.group(1) if m else None
            scheme = scheme or ("PE-RUC" if doc and len(doc) == 11 else None)
        key = (party_id, name, scheme, doc)
        if key in self._cache:
            return self._cache[key]
        if self.is_natural(scheme, doc):
            tok = f"NP-{self.token(doc)}"
            out = Party(tok, f"Natural person {tok}", None, True)
        else:
            out = Party(party_id or "", name, doc, False)
        self._cache[key] = out
        return out


def pseudonymise_release(rel: dict, pseudo: Pseudonymiser) -> dict:
    """Return a copy of an OCDS release with natural persons pseudonymised everywhere.

    Used for anything written back as JSON (e.g. the versioned sample in ``data/sample``).
    """
    import copy

    rel = copy.deepcopy(rel)
    mapping: dict[str, Party] = {}
    for party in rel.get("parties") or []:
        ident = party.get("identifier") or {}
        p = pseudo.party(party.get("id"), party.get("name"), ident.get("scheme"), ident.get("id"))
        mapping[party.get("id")] = p
        if p.is_natural_person:
            party["id"], party["name"] = p.id, p.name
            party["identifier"] = {"scheme": "PSEUDONYM", "id": p.id}
            party.pop("address", None)
            party.pop("contactPoint", None)

    def fix(org: dict) -> None:
        p = mapping.get(org.get("id")) or pseudo.party(org.get("id"), org.get("name"), None, None)
        if p.is_natural_person:
            org["id"], org["name"] = p.id, p.name

    tender = rel.get("tender") or {}
    for org in tender.get("tenderers") or []:
        fix(org)
    for bid in (rel.get("bids") or {}).get("details") or []:
        for org in bid.get("tenderers") or []:
            fix(org)
    for award in rel.get("awards") or []:
        for org in award.get("suppliers") or []:
            fix(org)
    return rel
