# Corvus release checklist

CI covers unit, security, fuzz and e2e tests plus an install-and-launch smoke test
(`scripts/smoke-installer.ps1`). These steps need a human.

## Before tagging
1. `npm run guard && npm run lint && npm test`, then `cd frontend && npx playwright test`.
2. Bump the version in `frontend/package.json` and `backend/pyproject.toml`.
3. Close Corvus, then run `npm run dist` (Developer Mode on).
4. Run `powershell ./scripts/smoke-installer.ps1`.

## Update from the previous release
1. Install the previous release from GitHub and start it once. Send a chat message and create a memory.
2. Publish the new draft release with **all three** files from the same build: `Corvus-Setup-x.y.z.exe`, its `.exe.blockmap`, and `latest.yml`.
3. In the old install, go to Settings → About & Updates → check for updates. It should download, restart, and show the new version.
4. Confirm the chat history and memory survived the update. Confirm plugins that were enabled stay loaded and are not asking for re-approval.

## Spot checks in the packaged app
- Ask "read this page then open example.com" on any page. A confirmation card naming the web page should appear.
- Delete a test file through chat. It should land in the Recycle Bin.
- Settings → Privacy & Data: Export → Delete all my data → Import with the same passphrase. Conversations should be back.
- With a cloud provider selected, "what's in my clipboard?" should ask first. The egress table should list the call.
