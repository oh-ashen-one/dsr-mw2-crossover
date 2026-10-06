"""Give transient gun requests priority over the persistent precision hold."""


def prioritize_requests(conditions):
    prefix = [condition.next_state_id for condition in conditions[:4]]
    if prefix == [9000, 9001, 9002, 9003]:
        return False
    if prefix != [9003, 9000, 9001, 9002]:
        raise ValueError('Unexpected idle gun dispatch; preserving action data')
    conditions[:4] = conditions[1:4] + conditions[:1]
    return True
