"""Original internal requests; emitted only by the M9 input adapter."""
from soulstruct.base.ezstate.esd.functions import *

class State_8000(State):
    """8000: Internal M9 request dispatch template."""
    def test(self):
        if GetEquipWeaponCategory(1) == 46 and IsAtkRequest(37):
            return State_9000
        if GetEquipWeaponCategory(1) == 46 and IsAtkRequest(38):
            return State_9001
        if GetEquipWeaponCategory(1) == 46 and IsAtkRequest(39):
            return State_9002

class State_9000(State):
    """9000: Filled from native firing state by the package builder."""

class State_9001(State):
    """9001: Filled from native reload state by the package builder."""

class State_9002(State):
    """9002: Filled from native reload state by the package builder."""

class State_8002(State):
    """8002: Scoped raised-gun hold, dispatched only from idle."""
    def test(self):
        if GetEquipWeaponCategory(1) == 46 and IsPrecisionShoot():
            return State_9003

class State_8003(State):
    """8003: Leave the hold pose immediately on release/context change."""
    def test(self):
        # Action requests are transient/consumed on entry. Native precision
        # mode is held by the gated aim adapter and cleared on release/context.
        if IsPrecisionShoot() == 0:
            return State_0

class State_9003(State):
    """9003: Filled from native action lifecycle by the package builder."""

class State_0(State):
    """0: Existing native idle destination, never installed from this template."""

class State_8001(State):
    """8001: Native direct one-hand evade rules for interruptible reloads."""
    def test(self):
        if IsAtkRequest(42) and GetStamina() > 10 and GetWeaponSwitchState() == 1:
            return State_36
        if IsAtkRequest(15) and GetStamina() > 10 and GetWeaponSwitchState() == 1:
            return State_32
        if IsAtkRequest(16) and GetStamina() > 10 and GetWeaponSwitchState() == 1:
            return State_33
        if IsAtkRequest(18) and GetStamina() > 10 and GetWeaponSwitchState() == 1:
            return State_34
        if IsAtkRequest(17) and GetStamina() > 10 and GetWeaponSwitchState() == 1:
            return State_35
        if IsAtkRequest(10) and GetStamina() > 10 and GetWeaponSwitchState() == 1:
            return State_38

class State_32(State):
    """32: Existing native evade destination; never installed from this template."""
class State_33(State):
    """33: Existing native evade destination; never installed from this template."""
class State_34(State):
    """34: Existing native evade destination; never installed from this template."""
class State_35(State):
    """35: Existing native evade destination; never installed from this template."""
class State_36(State):
    """36: Existing native evade destination; never installed from this template."""
class State_38(State):
    """38: Existing native backstep destination; never installed from this template."""
