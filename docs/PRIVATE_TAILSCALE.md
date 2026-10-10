# One colleague, private Tailscale sharing

October 10 activation update: Curtis separately approved a private HTTPS listener
for already-authorized devices on the existing account. Chess now uses a separate
8444 listener and loopback backend8001; existing443/8443 services were preserved.
Host-local HTTPS/API/WebSocket acceptance passed. No colleague invite, access-rule
change or remote-phone verification occurred. The foreground processes have no
new autostart. The account/access changes in the colleague guide below still
require their own approval.

Supported scope: **Curtis plus one trusted colleague, one match at a time**.
There is no Lounge sign-in or per-seat ownership yet. Both people can move either
human seat and control shared matches. Everyone allowed through the private link
must be trusted. This is a two-person support limit, not a concurrent-user quota.
Use a separate disposable practice database, not an archive containing private games.

The default stays loopback-only. `LOUNGE_NETWORK_MODE` is an explicit opt-in;
`LOUNGE_HOSTED_MODE=1` and `LOUNGE_DEPLOYMENT=hosted` still refuse startup.
Never use Funnel, a public tunnel, router port forwarding or a wildcard bind.
No hosting subscription or paid inference is required for Human/Stockfish play.

## Prepare locally (does not share anything)

From the repository, build the web app: `cd apps/web`, `npm ci`, `npm run build`,
then return to the repository. Use the existing Python environment/dependencies.
On Windows PowerShell:

```powershell
$env:PYTHONPATH = 'services/api'
$env:DATABASE_URL = 'sqlite+aiosqlite:///./.runtime/private-practice.db'
$env:LOUNGE_DEPLOYMENT = 'local'
$env:LOUNGE_HOSTED_MODE = '0'
$env:LOUNGE_PORT = '8001'
.venv\Scripts\python.exe -m lounge_api.serve --check
```

`--check` validates settings without binding, starting workers, opening the database
or changing Tailscale. On macOS/Linux use `export NAME=value` and
`.venv/bin/python -m lounge_api.serve`. Configure your existing Stockfish path.
Keep `.env.local` on the host. Never put API keys in Vite variables, URLs or messages.
For tonight, leave model provider keys unset and choose Human or Stockfish.

## Recommended phone path: private HTTPS Serve

The following activation/account steps need Curtis's approval; the agent has not
installed, signed in, invited anyone, changed access policy or enabled Serve.

1. Install/sign into Tailscale on the host and colleague's computer/phone. In the
   Tailscale admin console, share **only this host device** with the colleague's
   exact account; they accept the invite. Inspect existing grants/ACLs first and
   restrict access to this device's approved HTTPS port. Device sharing alone may expose other
   services allowed by the tailnet policy. Do not replace a policy blindly.
2. Read `tailscale status`, `tailscale ip -4` and `tailscale serve status`. Confirm
   the exact host's MagicDNS `.ts.net` name and the two account login names.
   Enabling HTTPS may require the Tailscale admin flow; approve it separately.
   Preserve existing Serve listeners. This host already has unrelated private
   Serve services on 443 and 8443; do not overwrite them. Agree an unused HTTPS
   port (8444 in the example below), verify it is unused, and approve only that
   new listener and its narrowly scoped access rule.
3. Configure the app with the real values (examples below are placeholders):

```powershell
$env:LOUNGE_NETWORK_MODE = 'tailscale-serve'
$env:LOUNGE_BIND_HOST = '127.0.0.1'
$env:LOUNGE_PRIVATE_ORIGINS = 'https://chess-host.example-tail.ts.net:8444'
$env:LOUNGE_TAILSCALE_USERS = 'curtis@example.com,colleague@example.com'
.venv\Scripts\python.exe -m lounge_api.serve --check
.venv\Scripts\python.exe -m lounge_api.serve
```

4. After approval, in another terminal run
   `tailscale serve --https=8444 http://127.0.0.1:8001`. Use foreground mode for the
   first test; Ctrl+C stops that Serve session. Do not add `--bg` without approval.
   Check `tailscale serve status` and confirm there is no public Funnel exposure.
5. Both users enable Tailscale, then open the exact HTTPS URL printed by Serve.
   The same origin serves the board, API and secure WebSocket. On a phone use
   Safari on iPhone or Chrome on Android. With the phone-support build,
   use Safari Share > Add to Home Screen, or Chrome's Install/Add to Home screen.
   Keep Tailscale enabled when launching the installed app.
   See [phone acceptance](PHONE_ACCEPTANCE.md) for the remaining physical-device
   checks. Automated browser emulation does not verify an actual home-screen install.

The backend stays on loopback. Serve supplies `Tailscale-User-Login`; the app
requires one of the two configured logins and the exact HTTPS Host/Origin. Missing,
tagged-device or other-user identities are denied. This trusts the host's local
processes and genuine Serve proxy, not arbitrary forwarded headers. Uvicorn proxy
header rewriting is disabled. Do not add another proxy in front of this configuration.

## Optional direct Tailscale address (computer diagnostic path)

For a direct private HTTP connection, configure the actual host Tailscale IP and
each approved device's source Tailscale IP. Phones need HTTPS Serve for installation.

```powershell
$env:LOUNGE_NETWORK_MODE = 'tailscale'
$env:LOUNGE_BIND_HOST = '100.100.10.1'
$env:LOUNGE_PRIVATE_PEERS = '100.100.10.1,100.100.10.2'
$env:LOUNGE_PRIVATE_ORIGINS = 'http://100.100.10.1:8001'
.venv\Scripts\python.exe -m lounge_api.serve --check
# Start only after approving the device addresses and any required firewall rule:
.venv\Scripts\python.exe -m lounge_api.serve
```

The colleague opens `http://100.100.10.1:8001`, not their own device's address.
An origin is **scheme + host + port**, not the client's source IP. Exact peer IPs
gate network requests independently of CORS; `X-Forwarded-For` cannot bypass this.
Do not allow a whole IP range. Any Windows firewall rule must be narrowly scoped
to this Tailscale interface, port and approved peers, and approved before creation.
Use the launcher above, not a custom Uvicorn command that trusts proxy headers.

## Verify together and stop sharing

- First use two Human seats and Start paused; open the same game URL on both
  devices, Resume, play e2-e4, and confirm both show the same board and move list.
- Test both Wi-Fi and the phone's intended connection with Tailscale enabled.
  An unshared device and a third Tailscale account must fail. A different browser
  origin must fail HTTP mutation and WebSocket access.
- Background/restore the phone and confirm it resynchronizes before moving.
  Install, close and reopen from the home screen; explicitly check audible sound.
  Real-device installation/audio and actual two-device access require this test.
- Provider keys remain on the host and are not returned in snapshots/catalogs.
  Trusted users can still trigger paid provider calls if the host enables them;
  there is no hard spend cap yet. Runner credential issuance, batch/Model Lab,
  diagnostics and API documentation routes are blocked in private sharing mode.
- When the host sleeps, powers off, loses internet, or stops the app/Serve, the
  shared board cannot play. A home-screen icon does not make the server permanent.
  Pause the match before stopping; persistence keeps the game, not a live service.
- Ctrl+C the app and foreground Serve; revoke the colleague's device share when
  finished. Inspect Serve status before/after; never reset unrelated Serve config.

Automated checks cover configuration rejection, source-IP/Host/Origin fencing,
WebSockets, proxy-header spoofing, admin-route denial and a provider-secret canary.
No live Tailscale pairing, TLS certificate, ACL or physical-phone acceptance has
been verified here. `tailscale` 1.102.2 is installed on the Windows host. The initial
restricted status check could not reach its daemon; an approved read-only host
check subsequently confirmed the service is Running/Automatic, both exit codes
are zero, and the device is connected. Existing Serve listeners are tailnet-only
on 443 and 8443; no Funnel exposure was reported. No service or network setting
was changed. No service start or reinstall is needed. The next action requires
approval of the colleague account, reviewed device-sharing/access policy and a
new, unused HTTPS Serve port; existing services must remain intact.

Official references checked October 10, 2026:
[device sharing](https://tailscale.com/docs/features/sharing),
[Serve and identity headers](https://tailscale.com/docs/features/tailscale-serve),
[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve).
