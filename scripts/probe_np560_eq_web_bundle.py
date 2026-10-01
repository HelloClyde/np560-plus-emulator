#!/usr/bin/env python3
"""Owned real Web launch for a selected default-v6 or experimental-v8 ROM bundle."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from urllib.request import urlopen

from probe_np560_web_lifecycle import request, wait_until
from probe_np560_matrix_route import WebBridge, RouteStep, replay_step, diagnostic_failure
from probe_np560_checkpoint_boot import assess
from verify_np560_toolbar_frames import expected_from_package
from probe_np560_npe_action_target import wait_for_direction_path


def scene_position(status):
    """Original world coordinates include viewport offsets, not just sprites."""
    position = {field: int(status[field]) for field in
                ('current_x', 'current_y', 'current_offset_x', 'current_offset_y',
                 'current_map_index', 'current_direction')}
    position['world_x'] = position['current_x'] + position['current_offset_x']
    position['world_y'] = position['current_y'] + position['current_offset_y']
    return position


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('qemu', 'firmware', 'bundle', 'nand', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--npe-title-check', action='store_true',
                        help='navigate the original menu to its first NPE title on this disposable instance')
    parser.add_argument('--package', type=Path)
    parser.add_argument('--startup-card-reference', type=Path)
    parser.add_argument('--npe-scene-check', action='store_true',
                        help='after title, start Hero and verify four directional moves; no save')
    parser.add_argument('--npe-exit-check', action='store_true',
                        help='after scene checks, open/cancel game menu and return to desktop')
    parser.add_argument('--native-sound-off', action='store_true',
                        help='use the original settings UI in this unsaved instance before NPE')
    parser.add_argument('--mp3-after-game-reference', type=Path,
                        help='verified LONG22 selected-row gray5 reference, after 29 Down contacts')
    args = parser.parse_args()
    if args.npe_exit_check and not args.npe_scene_check:
        parser.error('NPE exit check requires --npe-scene-check')
    if args.mp3_after_game_reference and not args.npe_exit_check:
        parser.error('MP3 after game requires --npe-exit-check')
    if args.native_sound_off and not args.npe_title_check:
        parser.error('native sound setting requires --npe-title-check')
    if args.npe_scene_check and not args.npe_title_check:
        parser.error('NPE scene check requires --npe-title-check')
    if args.npe_title_check and (not args.package or not args.startup_card_reference):
        parser.error('NPE check requires package and startup-card-reference')
    if os.name != 'posix':
        parser.error('run in WSL/Linux')
    args.output.mkdir(parents=True, exist_ok=False)
    runs = args.output/'runs'
    expected = json.loads((args.bundle/'manifest.json').read_text(encoding='utf-8'))
    rom_version = expected['rom_mp3_hle']['version']
    if rom_version not in (6, 8):
        parser.error(f'unsupported player ROM HLE version: {rom_version}')
    token = 'owned-player-web-probe'
    command = [sys.executable, '-u', str(Path(__file__).parent/'web/np560_web.py'),
               '--qemu', str(args.qemu), '--firmware', str(args.firmware),
               '--soc-rom-bundle', str(args.bundle),
               '--nand-checkpoint', str(args.nand), '--boot-mode', 'firmware-vma03',
               '--instruction-clock', '--icount-shift', '0', '--realtime',
               '--host', '127.0.0.1', '--port', '0', '--run-log-dir', str(runs),
               '--shutdown-token', token]
    if rom_version == 8:
        command += ['--experimental-eq']
    if args.npe_scene_check:
        command += ['--full-control-observers']
    result = dict(passed=False, browser_visual_verified=False, playback_verified=False,
                  command=command)
    with (args.output/'bridge.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            def serving():
                if process.poll() is not None:
                    raise RuntimeError('bridge exited before serving')
                for path in runs.glob('*/status.json'):
                    state = json.loads(path.read_text(encoding='utf-8'))
                    if state.get('phase') == 'serving':
                        return state
            state = wait_until(serving, timeout=45)
            root = 'http://127.0.0.1:'+str(state['port'])
            code, health = request(root, '/api/health')
            assert code == 200 and health['qemu_alive'] and health['bridge_pid'] == process.pid
            result['health'] = health
            with urlopen(root, timeout=5) as response:
                html = response.read().decode('utf-8')
            assert '选项设置页用 F4 返回播放页' in html
            code, snapshot = request(root, '/api/state')
            assert code == 200 and snapshot['soc_rom_sha256'] == expected['rom_sha256']
            assert snapshot['nand_save_enabled'] is False
            result['snapshot'] = snapshot
            base = expected['rom_mp3_hle']['base']
            marker_count = len(expected['rom_mp3_hle']['targets'])
            code, memory = request(root, f'/api/state?source=code&base={base}&size={16*marker_count}')
            assert code == 200
            markers = base64.b64decode(memory['frame'])
            for index in range(marker_count):
                assert struct.unpack_from('<8H', markers, index*16) == (
                    0xf00, 0xc620, 0x504d, 0x484c, rom_version, index, 0, 0)
            result['guest_marker_sha256'] = hashlib.sha256(markers).hexdigest()
            if args.npe_title_check:
                web = WebBridge(root, 10)
                reference = args.startup_card_reference.read_bytes()
                assert len(reference) == 240*120
                result['startup_reference_sha256'] = hashlib.sha256(reference).hexdigest()
                toolbar, _ = expected_from_package(args.package)
                def read_state():
                    value = web.get_json('/api/state')
                    failure = diagnostic_failure(value['registers'])
                    if failure:
                        raise RuntimeError(failure)
                    return value
                def startup():
                    value = read_state()
                    return base64.b64decode(value['frame']) == reference
                wait_until(startup, timeout=150)
                route = result['npe_route'] = []
                def key(name, index, event):
                    route.append(replay_step(web, RouteStep(name,index,event),
                        press_timeout=30, release_timeout=30, poll_interval=.05,
                        settle=1, pulse_duration=None if args.npe_scene_check else .15))
                key('dismiss-startup',53,0x86)
                wait_until(lambda: assess(read_state(), toolbar[1])['passed'], timeout=90)
                code, sound = request(root, '/api/state?source=memory&base=0x50b87a&size=2')
                assert code == 200
                result['native_sound_off'] = int.from_bytes(base64.b64decode(sound['frame']), 'little')
                if args.native_sound_off:
                    assert result['native_sound_off'] == 0, 'settings route expects sound-on seed'
                    settings_steps = [('settings-right-'+str(i),29,0x81) for i in range(4)]
                    settings_steps += [('speech-down',37,0x83),('speech-open',53,0x86)]
                    settings_steps += [('effect-down-'+str(i),37,0x83) for i in range(4)]
                    settings_steps += [('effect-open',53,0x86),('effect-off',37,0x83),
                                       ('effect-confirm',53,0x86),('settings-exit',55,0xb0)]
                    for step in settings_steps:
                        key(*step)
                    wait_until(lambda: assess(read_state(), toolbar[1])['passed'], timeout=90)
                    code, sound = request(root, '/api/state?source=memory&base=0x50b87a&size=2')
                    assert code == 200
                    result['native_sound_off'] = int.from_bytes(base64.b64decode(sound['frame']), 'little')
                assert result['native_sound_off'] == 1, 'NPE sound decoder is still unavailable'
                for step in (('start',55,0xb0),('entertainment',53,0x86),
                             ('game-world',37,0x83),('npe-list',53,0x86),
                             ('first-game',53,0x86)):
                    key(*step)
                def title():
                    value = read_state()
                    if 'NPE_GAME_CONTROL=LIVE:m0007/' in value['registers']:
                        return value
                title_state = wait_until(title, timeout=60)
                result['npe_title'] = title_state
                (args.output/'npe-title.gray5').write_bytes(base64.b64decode(title_state['frame']))
                result['npe_scope'] = 'first game title, native sound-off; not full gameplay or NPE sound'
                if args.npe_scene_check:
                    key('new-journey',53,0x86)
                    def scene():
                        value = read_state()
                        if 'NPE_GAME_CONTROL=LIVE:m0001/' in value['registers']:
                            return value
                    wait_until(scene, timeout=60)
                    observations = result['npe_scene'] = []
                    def capture_position(name, expected_xy):
                        value = scene()
                        assert value, 'game left scene mode'
                        status = web.get_json('/api/key-status')
                        position = scene_position(status)
                        observations.append(dict(name=name,position=position,key_status=status))
                        (args.output/(name+'.gray5')).write_bytes(base64.b64decode(value['frame']))
                        assert (position['world_x'],position['world_y']) == expected_xy, position
                        if len(observations) > 1:
                            assert position['current_map_index'] == observations[0]['position']['current_map_index']
                    capture_position('scene-initial',(8,12))
                    for name,index,event,xy in (
                        ('scene-down',37,0x83,(8,13)), ('scene-right',29,0x81,(9,13)),
                        ('scene-left',45,0x80,(8,13)), ('scene-up',61,0x82,(8,12))):
                        before = web.get_json('/api/key-status')
                        key(name,index,event)
                        wait_for_direction_path(web, before, name[len('scene-'):],
                                                timeout=60, poll_interval=.1)
                        capture_position(name,xy)
                    result['npe_scope'] = 'Hero new scene and four moves, native sound-off; no save/full gameplay/audio proof'
                    if args.npe_exit_check:
                        before_menu = scene_position(web.get_json('/api/key-status'))
                        key('game-menu',4,0x8e)
                        def menu():
                            value = read_state()
                            if 'NPE_GAME_CONTROL=LIVE:m0006/' in value['registers']:
                                return value
                        menu_state = wait_until(menu, timeout=60)
                        result['npe_menu'] = menu_state
                        (args.output/'game-menu.gray5').write_bytes(base64.b64decode(menu_state['frame']))
                        key('cancel-game-menu',4,0x8e)
                        wait_until(scene, timeout=60)
                        assert scene_position(web.get_json('/api/key-status')) == before_menu
                        key('exit-to-desktop',55,0xb0)
                        def desktop():
                            value = read_state()
                            if assess(value, toolbar[1])['passed']:
                                return value
                        desktop_state = wait_until(desktop, timeout=90)
                        result['npe_exit_desktop'] = desktop_state
                        (args.output/'exit-desktop.gray5').write_bytes(base64.b64decode(desktop_state['frame']))
                        result['npe_scope'] += '; F4 menu/cancel preserves position and Start returns to desktop'
                        if args.mp3_after_game_reference:
                            file_reference = args.mp3_after_game_reference.read_bytes()
                            assert hashlib.sha256(file_reference).hexdigest() == '7468d581c323c9c8482e02899a7de990bbd4e64b12ca567fd6bb28c976b23fc0'
                            for step in (('music-start',55,0xb0),('music-entertainment',53,0x86),
                                         ('music-open',53,0x86),('music-file',60,0xe2),('music-parent',53,0x86)):
                                key(*step)
                            for index in range(29):
                                key('music-file-down-'+str(index),37,0x83)
                            selected = read_state()
                            (args.output/'mp3-selected.gray5').write_bytes(base64.b64decode(selected['frame']))
                            assert base64.b64decode(selected['frame']) == file_reference, 'unexpected music file selection'
                            key('music-play',53,0x86)
                            for index in range(7):
                                key('music-volume-'+str(index),61,0x82)
                            def audible_packet():
                                code, audio = request(root, '/api/audio')
                                assert code == 200
                                raw = base64.b64decode(audio['pcm'])
                                if audio.get('enabled') and any(raw):
                                    return audio
                            first = wait_until(audible_packet, timeout=45)
                            time.sleep(3)
                            second = wait_until(audible_packet, timeout=45)
                            assert first['stream_id'] == second['stream_id']
                            assert first['generation'] == second['generation']
                            assert second['next_frame'] > first['next_frame']
                            result['mp3_after_game'] = {'first':first, 'second':second,
                                'scope':'actual advancing nonzero DAC packets; not continuous capture or browser listening'}
                            music_state = read_state()
                            (args.output/'mp3-playing.gray5').write_bytes(base64.b64decode(music_state['frame']))
            code, reply = request(root, '/api/control', {'action':'shutdown', 'token':token})
            assert code == 200, reply
            assert process.wait(timeout=20) == 0
            final_states = [json.loads(p.read_text(encoding='utf-8')) for p in runs.glob('*/status.json')]
            result['final_states'] = final_states
            assert len(final_states) == 1 and final_states[0]['phase'] == 'stopped'
            assert not Path('/proc/'+str(health['qemu_pid'])).exists()
            result['passed'] = True
        except Exception as error:
            result['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            (args.output/'report.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'], output=str(args.output))))


if __name__ == '__main__':
    main()
