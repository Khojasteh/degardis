### Applying a pattern

Use a `pattern` step when the same small procedure belongs in more than one
workflow. It applies the named reusable procedure at this point in the route.

| Field | Required | Meaning |
| --- | --- | --- |
| `pattern` | Yes | Pattern identifier. |
| `next` | Yes | Next step identifier. |
| `with` | No | Values supplied to the pattern's inputs. |

```yaml
check-sources:
  pattern: verify-attribution
  with:
    claims: {from: result.inspection.claims}
  next: write-summary
```

The pattern named must be one the manifest selects, and it must expand into at
least one procedure item; a pattern step that produces no work is reported.

A pattern application declares no `effects` of its own. The effects belong on
the procedure items inside the pattern, which are the steps that actually touch
something, so a requirement selecting on effects finds the work rather than the
place it was invoked from.
