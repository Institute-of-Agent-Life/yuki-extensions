# Maintenance route intake probe

Diagnostic Rust consumer of the pinned public CORE-035 SDK. Reads two original
selected events and sends model.open and extraction preview with their returned
versions. Writes each actual result/error to the private fixture directory.
It is not an installable plugin or an EXT-034 acceptance claim. It never
acknowledges source erasure. Run through `ci/maintenance_intake.py` on Windows.
