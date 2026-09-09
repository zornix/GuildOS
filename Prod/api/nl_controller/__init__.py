"""NL chapter controller — approval-gated natural-language command requests.

There is NO parser and NO auto-execution: a request is recorded with empty
proposed_actions, must be approved by a holder of nl_controller:approve, and
execution (when it exists) will only ever call other domains' service APIs —
never duplicate their logic. The operations engine (api/services/operations.py)
is the closest precursor and will be one of the orchestrated targets.
"""
