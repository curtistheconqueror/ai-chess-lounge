# ADR 0037: opt-in trusted Tailscale practice

Status: private two-person preparation, not hosted accounts or public deployment.

Curtis authorized a no-paid-hosting route for one trusted colleague. Keep hosted
startup blocked; add separate local, direct-Tailscale and loopback-Serve network
settings. The approved launcher disables forwarded-header rewriting. Direct mode
requires an exact Tailscale bind IP and exact source peers. Serve mode binds IPv4
loopback and requires one of at most two explicit Tailscale login headers supplied
by Serve. Only local processes can spoof those headers; the host is trusted.
No client IP is inferred from untrusted forwarding headers.

Private modes separately enforce exact Host and browser Origin for HTTP and
WebSockets. Browser origins use scheme/host/port, not the visitor's source address.
Runner credential, batch, diagnostics and API documentation routes are blocked.
Game controls remain shared trusted-operator controls: there is no per-user seat
ownership, sign-in or isolation. Two people is a supported practice scope, not a
quota or completed hosted acceptance. Use a separate practice database.

Actual installation, sign-in, invitations, ACL/firewall changes and Serve activation
remain approval steps; code/configuration tests do not prove two-device connectivity.
Never use Funnel. Supabase, Cloudflare and paid runtime work are deferred. Hosted
Auth and ownership must still pass the independent release gates before publication.
