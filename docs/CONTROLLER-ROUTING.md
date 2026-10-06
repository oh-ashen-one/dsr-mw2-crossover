# Controller routing correction

The PS button opening Steam does not establish that DSR receives gamepad input. A source-built console diagnostic reproduced this package defect while DSR was closed: ten slot 0 reads returned error 1167 through the original proxy's renamed retail backend, while the installed CrossOver system XInput1.4 module returned success.

The proxy now reads states from `C:\windows\system32\xinput1_4.dll`. Capabilities, vibration, enable, battery, keystroke and extended-state exports forward to that same installed module. No controller packets are remapped or synthesized. Legacy audio/guide functions absent from Wine preserve their existing retail forwarding. The original retail DLL remains backed up and restored by the private installer.

After rebuilding, all ten slot 0 state and capability samples succeeded. The console probe checks that the five named controller forwards and extended-state ordinal resolve to the system module, and compares gamepad bytes when both reads share a packet number. No vibration, input synthesis, game launch or registry/Steam setting change is performed by the probe. Physical controller identity and buttons inside DSR still require owner validation.

Rebuild with `python3 -B -m tools.native_input_trial build`, then use the normal offline owner preparation. The source-built `console` diagnostic requires the existing guarded private trial install and must be followed by restoration; it is not a game or a substitute for gameplay acceptance. Keep generated binaries, receipts and logs local.

Reference: Wine's [XInput1.4 export contract](https://github.com/wine-mirror/wine/blob/master/dlls/xinput1_4/xinput1_4.spec) and Valve's [Steam Input emulation documentation](https://partner.steamgames.com/doc/features/steam_controller/steam_input_gamepad_emulation_bestpractices). The defect and successful comparison above come from local measurements, not an assumption that every controller/platform is supported.
