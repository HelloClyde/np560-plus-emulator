#!/usr/bin/env python3
"""Inspect Hero's equipment through native slot-three load on an owned instance.

No save/export or guest RAM writes. Requires the pinned battle-save NAND and
full observers. This only navigates and captures; screenshots need review.
"""
import argparse
import base64
import json
from pathlib import Path

from probe_np560_matrix_route import WebBridge, RouteStep, replay_step, diagnostic_failure
from probe_np560_checkpoint_boot import assess, save_snapshot
from probe_np560_web_lifecycle import wait_until
from verify_np560_toolbar_frames import expected_from_package


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--startup-card-reference', type=Path, required=True)
    p.add_argument('--owned-bridge-pid', type=int, required=True)
    p.add_argument('--stage', choices=('load', 'observe', 'items', 'equipment', 'confirm', 'back', 'magic', 'menu-magic', 'magic-character', 'magic-cast', 'encounter', 'battle-magic', 'battle-confirm', 'battle-observe', 'battle-attack', 'battle-options', 'battle-items', 'battle-defend', 'battle-attack-from-flag'), default='load')
    p.add_argument('--encounter-square', action='store_true', help='six-step rectangle instead of alternating two tiles')
    p.add_argument('--desktop-ready', action='store_true', help='resume load from a verified native desktop, without dismissing the startup card')
    args = p.parse_args()
    web = WebBridge(args.root, 15)
    health = web.get_json('/api/health')
    assert health['bridge_pid'] == args.owned_bridge_pid and health['qemu_alive']
    assert health['artifacts']['nand_checkpoint']['sha256'] == '6e4e2672fc244fd1bb1f1745059790ce8031208e5775c345ca2c5e9742d81133'
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(health=health, passed=False, host_guest_memory_writes=0, steps=[])

    def state():
        s = web.get_json('/api/state')
        assert not s['nand_save_enabled']
        fault = diagnostic_failure(s['registers'])
        if fault:
            raise RuntimeError(fault)
        return s

    def capture(name):
        s = state()
        save_snapshot(args.output, name, s)
        # Read-only original skill workspace and three 0x94-byte character
        # records. These are sequential reads, not an atomic paused snapshot.
        for label, address, size in (('skill', 0x52730e, 0x90),
                                     ('characters', 0x5269df, 3 * 0x94),
                                     ('battle', 0x526450, 10 * 0x94),
                                     ('effects', 0x527920, 0x20)):
            memory = web.get_json(f'/api/state?source=memory&base={address}&size={size}')
            raw = base64.b64decode(memory['frame'], validate=True)
            assert len(raw) == size
            (args.output / f'{name}.{label}.bin').write_bytes(raw)
        print(name, flush=True)
        return s

    def mode(value):
        return f'NPE_GAME_CONTROL=LIVE:m{value:04x}/' in state()['registers']

    def key(name, index, event):
        report['steps'].append(replay_step(web, RouteStep(name, index, event),
            press_timeout=30, release_timeout=30, poll_interval=.05,
            settle=1, pulse_duration=None))
        capture(name)

    try:
        assert web.get_json('/api/key-status').get('full_control_observers') is True
        if args.stage == 'observe':
            capture('inspection')
            report['passed'] = True
            report['scope'] = 'read-only capture; no expected game mode or input'
            return
        if args.stage == 'encounter':
            if mode(6):
                key('close-menu',4,0x8e)
            wait_until(lambda: mode(1), timeout=60)
            pattern = ((37,0x83),(37,0x83),(29,0x81),(61,0x82),(61,0x82),(45,0x80)) if args.encounter_square else ((37,0x83),(61,0x82))
            for number in range(60 if args.encounter_square else 32):
                if not mode(1):
                    break
                index, event = pattern[number % len(pattern)]
                key('walk-'+str(number),index,event)
            capture('encounter-result')
            report['passed'] = True
            report['scope'] = 'bounded native movement; outcome requires screenshot review'
            return
        if args.stage != 'load':
            expected_mode = 3 if args.stage.startswith('battle-') else 1 if args.stage == 'magic' else 4 if args.stage in ('confirm', 'back') else 6
            assert mode(expected_mode), 'unexpected native menu mode'
            if args.stage == 'battle-magic':
                key('battle-left',45,0x80)
            if args.stage == 'battle-attack-from-flag':
                key('battle-up',61,0x82)
            if args.stage in ('battle-attack', 'battle-attack-from-flag'):
                key('battle-right',29,0x81)
            # Requires visual confirmation of the selected magic icon (options)
            # or the first row of the opened flag menu (defend).
            if args.stage in ('battle-options', 'battle-items', 'battle-defend'):
                for number in range(2 if args.stage == 'battle-defend' else 1):
                    key('battle-down-'+str(number),37,0x83)
            if args.stage == 'magic':
                key('menu',4,0x8e)
                wait_until(lambda: mode(6), timeout=60)
            if args.stage in ('magic', 'menu-magic'):
                key('magic-down',37,0x83)
            if args.stage in ('items', 'equipment'):
                for number in range(2 if args.stage == 'items' else 1):
                    key('down-'+str(number),37,0x83)
            if args.stage == 'back':
                key('back',4,0x8e)
            elif args.stage != 'battle-observe':
                key('open-'+args.stage,53,0x86)
            capture('inspection')
            report['passed'] = True
            report['scope'] = 'menu navigation only; visual review required'
            return
        if not args.desktop_ready:
            reference = args.startup_card_reference.read_bytes()
            assert len(reference) == 240 * 120
            wait_until(lambda: base64.b64decode(state()['frame']) == reference, timeout=150)
            key('00-dismiss', 53, 0x86)
        toolbar, _ = expected_from_package(args.package)
        wait_until(lambda: assess(state(), toolbar[1])['passed'], timeout=90)
        sound = web.get_json('/api/state?source=memory&base=5290106&size=2')
        # 50:B87A, native sound-off setting, read-only. ESAC is still absent.
        assert int.from_bytes(base64.b64decode(sound['frame']), 'little') == 1
        for step in [('01-start',55,0xb0),('02-entertainment',53,0x86),
                     ('03-game-world',37,0x83),('04-list',53,0x86),('05-hero',53,0x86)]:
            key(*step)
        wait_until(lambda: mode(7), timeout=60)
        for step in [('06-continue',37,0x83),('07-slots',53,0x86),
                     ('08-slot-two',37,0x83),('09-slot-three',37,0x83),('10-load',53,0x86)]:
            key(*step)
        wait_until(lambda: mode(1), timeout=60)
        report['loaded_position'] = web.get_json('/api/key-status')
        key('11-menu',4,0x8e)
        wait_until(lambda: mode(6), timeout=60)
        capture('12-menu-ready')
        report['passed'] = True
        report['scope'] = 'native slot-three load and menu capture; equipment not yet verified'
    finally:
        report['memory_capture_note'] = 'sequential read-only skill/character windows; not atomic, not a guest event trace'
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
