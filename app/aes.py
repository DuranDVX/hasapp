"""Advanced electronic signatures (AES) on PDFs.

ECT Act s13(1): where a law requires a signature and does not say which
type, only an AES meets it. In South Africa an AES comes from an accredited
provider (LAWtrust, also used through SigniFlow; the SA Post Office).

The app issues the PDF. The signer signs it in the provider's tool (or by
hand). The signed PDF comes back here and inspect() reports what it holds:
who signed, which certificate authority issued the certificate, when, and
whether the document is still intact after signing. The app does not hold a
LAWtrust trust root yet, so "accredited_issuer" is a name check only; a full
trust-chain check needs the provider's root certificate (ACCREDITED_ROOTS).
"""
import hashlib
import io
import logging

log = logging.getLogger("hasapp.aes")

# Issuer names of SAAA-accredited authentication service providers.
ACCREDITED_ISSUERS = ("lawtrust", "south african post office", "sapo")


def _name(n) -> str:
    try:
        return n.human_friendly
    except Exception:
        return str(n)


def _trust_roots() -> list:
    """Root certificates of accredited providers (PEM bundle in AES_TRUST_ROOTS)."""
    import os
    path = os.getenv("AES_TRUST_ROOTS", "")
    if not path or not os.path.exists(path):
        return []
    from asn1crypto import pem, x509 as ax509
    roots = []
    with open(path, "rb") as f:
        for _, _, der in pem.unarmor(f.read(), multiple=True):
            roots.append(ax509.Certificate.load(der))
    return roots


def inspect(data: bytes, original: bytes | None = None) -> dict:
    """Return {"signatures": [...], "contains_original": bool|None, "error": str}.

    A signature is "trusted" only when it chains to a root in AES_TRUST_ROOTS.
    The issuer name alone proves nothing: anyone can make a certificate with
    any name.
    """
    logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)
    out = {"signatures": [], "contains_original": None, "error": ""}
    if original:
        out["contains_original"] = data.startswith(original)
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext
    except Exception:
        out["error"] = "Signature check is not installed."
        return out
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
        sigs = list(reader.embedded_signatures)
    except Exception as e:
        out["error"] = f"This file could not be read as a PDF ({type(e).__name__})."
        return out
    for sig in sigs:
        item = {"field": sig.field_name, "signer": "", "issuer": "", "signing_time": "",
                "intact": False, "valid": False, "trusted": False, "coverage": "",
                "accredited_issuer": False}
        try:
            cert = sig.signer_cert
            item["signer"] = _name(cert.subject)
            item["issuer"] = _name(cert.issuer)
            item["accredited_issuer"] = any(a in item["issuer"].lower() for a in ACCREDITED_ISSUERS)
            roots = _trust_roots()
            # Explicit roots only: never trust the server's operating-system store.
            vc = ValidationContext(allow_fetching=False, trust_roots=roots)
            st = validate_pdf_signature(sig, vc)
            item["intact"], item["valid"], item["trusted"] = bool(st.intact), bool(st.valid), bool(st.trusted)
            item["coverage"] = getattr(st.coverage, "name", str(st.coverage))
            t = getattr(st, "signer_reported_dt", None) or getattr(sig, "self_reported_timestamp", None)
            item["signing_time"] = t.isoformat() if t else ""
        except Exception as e:
            log.info("signature check failed: %s", e)
            item["error"] = type(e).__name__
        out["signatures"].append(item)
    return out


def summary(result: dict) -> str:
    sigs = result.get("signatures") or []
    if not sigs:
        return "No digital signature found in this PDF."
    parts = []
    for s in sigs:
        ok = "intact" if s.get("intact") else "ALTERED or unreadable"
        acc = ("verified accredited issuer" if s.get("trusted")
               else "issuer named as accredited, chain not verified" if s.get("accredited_issuer")
               else "issuer not on the accredited list")
        parts.append(f"{s.get('signer') or 'Unknown signer'} ({s.get('issuer') or 'unknown issuer'}; {acc}; {ok})")
    return "; ".join(parts)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
