#pragma once
namespace dsr_mw2 {
// Slots follow GunKind: 0 M9, 1 Intervention, 2 SCAR-H, 3 M203.
bool shot_audio_load(const wchar_t* file,unsigned slot);
void shot_audio_play(unsigned slot);
void shot_audio_stop();
}
