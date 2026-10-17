# The body of a ruleset PUT or POST, from a ruleset as a GET returns it
# (baseline-ruleset-main-protection.json, or the live ruleset). Every restore
# in docs/_internal/RELEASING.md runs it with `jq -f`, so a change here
# changes them all; record it with the restore drill in that file.
#
# A PUT replaces the rules array wholesale, so the filter keeps every rule
# and every parameter a PUT takes, and a restore sends the saved value
# instead of leaving one to the server; bypass_actors keeps the admin-via-PR
# bypass. A GET can give a required check a null integration_id, and a PUT
# carrying one fails with HTTP 422 ("data matches no possible input"), so the
# filter drops a check's null keys. A PUT takes do_not_enforce_on_create (200
# with it set to false), so it is kept. The restore drill in RELEASING.md
# records both results.
{name, target, enforcement, conditions,
  rules: [.rules[] | if .type == "required_status_checks" then
    .parameters.required_status_checks |= map(with_entries(select(.value != null)))
  else . end],
  bypass_actors}
