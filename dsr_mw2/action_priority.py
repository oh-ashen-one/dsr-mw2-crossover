"""Give transient gun requests priority over the persistent precision hold."""
import copy


def prioritize_requests(conditions):
    prefix = [condition.next_state_id for condition in conditions[:4]]
    if prefix == [9000, 9001, 9002, 9003]:
        return False
    if prefix != [9003, 9000, 9001, 9002]:
        raise ValueError('Unexpected idle gun dispatch; preserving action data')
    conditions[:4] = conditions[1:4] + conditions[:1]
    return True


# Native crossbow aim (L1 quick-fire), shot and recovery states. The gun's
# transient requests are dispatched only from idle otherwise, so R2 and reload
# were dropped while the native crossbow path held the action machine.
NATIVE_CROSSBOW_STATES = (65, 67, 68)


def route_native_crossbow(states):
    """Prepend idle's exact fire/reload/empty-reload dispatch to the native crossbow states."""
    dispatch = states[0].conditions[:3]
    if [c.next_state_id for c in dispatch] != [9000, 9001, 9002]:
        raise ValueError('Unexpected idle gun dispatch; preserving action data')
    changed = False
    for number in NATIVE_CROSSBOW_STATES:
        conditions = states[number].conditions
        prefix = [c.next_state_id for c in conditions[:3]]
        if prefix == [9000, 9001, 9002]:
            continue
        if any(c.next_state_id in (9000, 9001, 9002, 9003) for c in conditions):
            raise ValueError('Unexpected gun routing in native crossbow state %d' % number)
        conditions[:0] = copy.deepcopy(dispatch)
        changed = True
    return changed
