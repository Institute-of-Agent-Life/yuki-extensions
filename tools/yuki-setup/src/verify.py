# Executed with isolated Python; all verification inputs except the archive are compiled into the binary.
import hashlib
import json
from pathlib import Path
import sys
import tempfile

archive, lock, manifest, signature, signer, dist_code, oci_code = sys.argv[1:]
pin = json.loads(lock)
with tempfile.TemporaryDirectory(prefix="yuki-setup-verify-") as temp:
    root = Path(temp)
    for name, value in {"oci-candidate.json":manifest, "oci-candidate.json.sig":signature,
                        "signer.pub":signer, "verify_dist.py":dist_code, "verify_oci.py":oci_code}.items():
        raw = value.encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != pin["artifacts"][name]:
            raise ValueError("packaged verification input differs: " + name)
        (root / name).write_bytes(raw)
    sys.path.insert(0, str(root))
    import verify_dist
    use_pinned_verifier(verify_dist)
    from verify_oci import verify_oci
    verified = verify_oci(archive, root / "oci-candidate.json", root / "signer.pub",
                          pin["source_commit"], pin["archive_sha256"], pin["platform"])
    if (verified["dirty"] or verified["published"] or not verified["nonroot_owner"]
            or verified["oci"]["roots"] != [pin["image_digest"]] or verified["readyz"]!="verified"):
        raise ValueError("unsupported candidate")
    print(pin["core_version"], pin["image_digest"], pin["platform"], sep="\n")
