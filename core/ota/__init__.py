"""Phase 29: OTA model update system. Verified, atomic on-device installs -
network download is deliberately NOT here (see tools/ota_download_and_apply.py):
this package has zero network dependencies, matching core/'s existing
zero-network property documented in docs/privacy.md."""
