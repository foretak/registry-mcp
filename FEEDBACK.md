# FEEDBACK

Every inbound signal about registry-mcp, one entry per item, newest first.
This is the input the day-45 decision gate (~2026-10-19, `BRREG_MCP_BUILD_PLAN.md`
§4.3) reads alongside the stats dashboard. Log the substance, not the sentiment:
what they asked for, what they tried, what stopped them, what they would pay for.

Format: `date · channel · who (handle or role) · what they said · what we did`.

## Open threads to watch

| Channel | Where | Since | Status |
|---|---|---|---|
| Reddit r/mcp | https://www.reddit.com/r/mcp/comments/1w7u6j0/ | 2026-09-05 | filtered on posting, then visible again the same day (modmail sent); first comment received |
| dev.to | five articles under https://dev.to/fargeroddotcom | 2026-09-04 | no comments yet |
| GitHub | https://github.com/foretak/registry-mcp/issues | 2026-09-04 | only our 3 seed issues |
| mcp.so | chatmcp/mcpso#3927 | 2026-09-04 | no reply |
| awesome-mcp-servers | punkpeye#13631 | 2026-09-04 | bot comment only (Glama badge) |
| Erhvervsstyrelsen | cvrselvbetjening@erst.dk (T16) | 2026-09-05 | application sent, reply due ~2026-09-23 |

## Entries

- 2026-09-05 · Reddit r/mcp · commenter on post 1 · asked whether an agent had ever misread `active` or an overdue date before the response shape was fixed · Kim replied honestly: no real users yet; the traps seen in tests were Companies House `open` for overseas entities, brreg returning 200 for deleted companies, and the silent zero-deadlines bug (T15e B1 / D-018). Signal: readers care about *how the tool fails*, not the feature list.
