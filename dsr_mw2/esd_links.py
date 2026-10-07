"""Per-machine ESD state links for Soulstruct 2.6.0 writes, plus a raw link checker.

Soulstruct's ESD.to_writer keeps ONE state-id -> offset table for the whole file,
so when two machines share state IDs (the player's c0000 machines 0 and 1 both
use 0-224) every condition is linked to the LAST machine's state of that number.
In c0000 that sends the master machine's damage, fall and death transitions into
machine 1's same-numbered action states: no hit reactions, no fall damage, and a
player frozen at 0 HP instead of dying. Talk ESDs share IDs across machines too.

`install()` replaces to_writer with a copy that links (and shares identical
conditions) only within each machine. `cross_machine_links(data)` reads raw ESD
bytes and lists every condition whose next-state pointer leaves its own machine.
"""
import copy

_PATCHED = False


def _fixed_to_writer(self):
    from soulstruct.base.ezstate.esd import core
    from soulstruct.utilities.binary import ByteOrder, RESERVED

    esd_name_length = len(self.esd_name) + 1 if self.esd_name else 0
    external = core.ESDExternalHeaderStruct.object_to_writer(
        self, byte_order=ByteOrder.LittleEndian, long_varints=self.LONG_VARINTS,
        esd_name_length=esd_name_length, state_machine_count=len(self.state_machines),
        game_version=[self.VERSION, self.VERSION],
        **core.EXTERNAL_HEADER_VARINT_ASSERTED[self.LONG_VARINTS])
    internal_cls = core.ESDInternalHeaderStruct64 if self.LONG_VARINTS else core.ESDInternalHeaderStruct32
    writer = internal_cls.object_to_writer(
        self, byte_order=ByteOrder.LittleEndian, long_varints=self.LONG_VARINTS,
        state_machine_count=len(self.state_machines), esd_name_offset=RESERVED,
        esd_name_length=esd_name_length, footer=[0, 0] if self.VERSION == 1 else [-1, -1])
    # Distinct objects per machine: a condition shared between machines would
    # otherwise be packed once and point into only one of them.
    machines = {index: copy.deepcopy(states) for index, states in self.state_machines.items()}
    for index, states in machines.items():
        core.StateMachineHeaderStruct.object_to_writer(
            states, writer, index=index, states_offset=RESERVED, state_count=len(states),
            states_offset_2=RESERVED)

    offsets = {index: {} for index in machines}
    all_states = []  # (machine, state), including each machine's trailing duplicate first state
    for index, states in machines.items():
        writer.fill_with_position("states_offset", obj=states)
        writer.fill_with_position("states_offset_2", obj=states)
        for state in states.values():
            offsets[index][state.state_id] = writer.position
            state.to_esd_writer(writer)
            all_states.append((index, state))
        if len(states) > 1:
            dummy = list(states.values())[0].copy()
            dummy.to_esd_writer(writer)
            all_states.append((index, dummy))
    external.fill("state_count", len(all_states), obj=self)

    conditions = {index: {} for index in machines}
    fresh = [state.pack_conditions(writer, offsets[index], conditions[index]) for index, state in all_states]
    external.fill("condition_count", sum(len(c) for c in conditions.values()), obj=self)
    external.fill("command_count", sum(s.pack_commands(writer, f) for (_, s), f in zip(all_states, fresh)), obj=self)
    external.fill("command_arg_count", sum(s.pack_command_args(writer, f) for (_, s), f in zip(all_states, fresh)), obj=self)
    external.fill("condition_pointers_offset", writer.position, obj=self)
    recurred = {index: set() for index in machines}
    pointers = sum(s.pack_condition_pointers(writer, conditions[index], recurred[index]) for index, s in all_states)
    external.fill("condition_pointers_count", pointers, obj=self)
    for (_, state), f in zip(all_states, fresh):
        state.pack_condition_test_data(writer, f)
    for (_, state), f in zip(all_states, fresh):
        state.pack_command_arg_data(writer, f)
    external.fill("tail_offset", writer.position, obj=self)
    if self.esd_name:
        writer.fill_with_position("esd_name_offset", obj=self)
        writer.append(self.esd_name.encode("utf-16-le") + b"\0\0")
    else:
        writer.fill("esd_name_offset", -1, obj=self)
    external.fill("unk_offset_1", writer.position, obj=self)
    external.fill("unk_offset_2", writer.position, obj=self)
    external.fill("internal_data_size", writer.position, obj=self)
    external.append(bytes(writer))
    return external


def install():
    """Use per-machine links for every ESD written in this process (call after configure())."""
    global _PATCHED
    from soulstruct.base.ezstate.esd.core import ESD
    ESD.to_writer = _fixed_to_writer
    _PATCHED = True


def cross_machine_links(data, esd_class):
    """Return [(machine, state_id, target_machine, target_state_id)] for links that leave their machine."""
    from soulstruct.base.ezstate.esd.condition import Condition, ConditionStruct
    from soulstruct.base.ezstate.esd.state import State
    starts, owners, links = [], {}, []
    state_reader, condition_reader = State.from_esd_reader.__func__, Condition.from_esd_reader.__func__

    def read_state(cls, reader):
        starts.append(reader.position)
        return state_reader(cls, reader)

    def read_condition(cls, reader):
        at = reader.position
        header = ConditionStruct.from_bytes(reader)
        reader.seek(at)
        links.append((len(starts) - 1, header.next_state_offset))
        return condition_reader(cls, reader)

    State.from_esd_reader = classmethod(read_state)
    Condition.from_esd_reader = classmethod(read_condition)
    try:
        esd = esd_class.from_bytes(data)
    finally:
        State.from_esd_reader = classmethod(state_reader)
        Condition.from_esd_reader = classmethod(condition_reader)
    order = [(m, sid) for m, states in esd.state_machines.items() for sid in states]
    if len(order) != len(starts):
        raise ValueError('ESD state walk disagrees with its machines')
    for (m, sid), at in zip(order, starts):
        owners[at] = (m, sid)
    bad = []
    for state_index, target in links:
        if target <= 0:
            continue
        if target not in owners:
            raise ValueError('Condition points outside the state table')
        m, sid = order[state_index]
        tm, tsid = owners[target]
        if tm != m:
            bad.append((m, sid, tm, tsid))
    return bad
