from api.rbac.services import permissions as svc


class _Counting:
    def __init__(self, sb):
        self._sb, self.calls = sb, 0

    def table(self, name):
        self.calls += 1
        return self._sb.table(name)


def test_second_lookup_uses_the_request_cache(sb_client, chapter_id, member_factory):
    member = sb_client.table("members").select("*").eq("id", member_factory()).single().execute().data
    counting = _Counting(sb_client)
    first = svc.get_member_permissions(member, sb=counting)
    after_first = counting.calls
    assert svc.get_member_permissions(member, sb=counting) == first
    assert svc.has_permission(member, "tasks:complete", sb=counting) in (True, False)
    assert counting.calls == after_first
