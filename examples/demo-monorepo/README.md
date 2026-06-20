# demo-monorepo

A tiny polyglot-style monorepo with a deliberate dependency chain, used to
demo CodeAtlas's PR intelligence and impact analysis:

```
auth/session.py  (verify_token)
        ▲
billing/invoice.py  (create_invoice → verify_token)
        ▲
admin/dashboard.py  (admin_overview → create_invoice)
```

A change to `auth.verify_token` therefore has a real blast radius into billing
(one hop) and admin (two hops).

## Demo commands

```bash
codeatlas index examples/demo-monorepo --db /tmp/demo.db

# What breaks if I change auth?
codeatlas explain-query "verify token" --db /tmp/demo.db

# Simulate a PR that edits auth and see the blast radius + suggested tests:
#   (make a commit changing auth/session.py on a branch, then)
codeatlas pr-analyze --base main --head HEAD --repo examples/demo-monorepo --db /tmp/demo.db
```

The impact panel / `pr-analyze` should surface `create_invoice` (billing) as a
downstream dependent and `tests/test_auth.py` as a relevant existing test.
