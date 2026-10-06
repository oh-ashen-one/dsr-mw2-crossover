# Window controls

Build the original helper with `python3 -B -m tools.build_window_controls` before owner preparation. It needs the existing MinGW compiler and objdump on PATH. The ordinary owner launcher then stages the hash-checked helper and starts it only after one private offline DSR process appears.

Initial preparation backs up the private `DarkSouls.ini` and selects a 1600×900 window. Subsequent preparations preserve resolution choices made by the owner. Original source installations, game saves and global Wine/macOS settings are untouched.

The helper enables a resize border on the private DSR window. Shortcuts exist only while that window is foreground:

| Shortcut on Mac | Action |
| --- | --- |
| Control + Option + 1 | Request 1280×720 |
| Control + Option + 2 | Request 1600×900 |
| Control + Option + 3 | Request 1920×1080 |
| Control + Option + M | Minimize the game to release mouse capture; restore from the Dock |
| Command + Tab | macOS app switching, independent of the helper |

Requested sizes are reduced if necessary to fit the monitor's work area. The helper does not inject code, read/write game memory, synthesize gameplay input, force focus, or warp/unclip the mouse. It exits when its game window/process closes. It never opens a game itself. Its hidden-window fixture changes only a window it creates; running that fixture through CrossOver still requires the user's local execution scope.

Verified: strict compilation/import audit, Python ownership/configuration tests, and a hidden-window resize/style fixture through the private CrossOver profile. **DSR resizing, physical shortcut response and render behavior after resizing still need an owner test.** Preparation does not reopen DSR. Mouse aiming remains captured during normal gameplay.

The implementation uses documented [Win32 window styles](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-styles) and [SetWindowLongPtrW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw). Wine's [macOS driver](https://github.com/wine-mirror/wine/blob/master/dlls/winemac.drv/window.c) maps `WS_THICKFRAME` to a resizable native window. These references explain the approach; they do not establish DSR runtime compatibility. No upstream source was copied for this helper.
