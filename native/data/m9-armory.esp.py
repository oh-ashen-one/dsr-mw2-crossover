"""Original native bonfire armory extension; normal soul purchases/equipment only."""
from soulstruct.darksouls1r.ezstate.esd import *


class State_8000(State):
    """8000: Menu extension template; original bonfire state remains authoritative."""
    def enter(self):
        AddTalkListData(menu_index=13, menu_text_id=90000001, required_flag=-1)

    def test(self):
        if GetTalkListEntryResult() == 13:
            return State_9000


class State_9000(State):
    """9000: Native armory purchase window with ordinary bonfire exit guards."""
    def enter(self):
        OpenRegularShop(11000, 11002)

    def test(self):
        if CompareBonfireState(0) == 1 or HasPlayerBeenAttacked() == 1 or IsPlayerDead() == 1:
            return State_49
        if (
            IsTalkingToSomeoneElse()
            or CheckSelfDeath()
            or IsCharacterDisabled()
            or IsClientPlayer() == 1
            or GetRelativeAngleBetweenPlayerAndSelf() > 120
            or GetDistanceToPlayer() > 8
            or GetPlayerYDistance() > 1
        ):
            return State_49
        if IsMenuOpen(11) == 0:
            return State_4


class State_4(State):
    """4: Existing native bonfire menu destination; not copied into output."""


class State_49(State):
    """49: Existing native shop cancellation destination; not copied into output."""
